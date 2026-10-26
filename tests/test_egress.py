import dataclasses
import importlib.util
from pathlib import Path
import ssl
import socketserver
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from crosscode.core import Config
from crosscode.evaluator import docker_command, runtime_descriptor
from crosscode.egress import restricted_broker, EgressSetupError

spec=importlib.util.spec_from_file_location('egress_proxy',Path(__file__).resolve().parents[1]/'docker/egress_proxy.py')
proxy=importlib.util.module_from_spec(spec)
with patch.object(socketserver,'UnixStreamServer',socketserver.TCPServer,create=True):
    spec.loader.exec_module(proxy)


class EgressTests(unittest.TestCase):
    def test_authority_allowlist(self):
        self.assertTrue(proxy.permitted_authority('en.wikibooks.org:443'))
        for value in ['example.com:443','127.0.0.1:443','en.wikibooks.org:80',
                      'en.wikibooks.org.evil.com:443','user@en.wikibooks.org:443']:
            self.assertFalse(proxy.permitted_authority(value))

    def test_only_public_addresses(self):
        self.assertTrue(proxy.public_address('8.8.8.8'))
        for value in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','192.168.1.1','224.0.0.1']:
            self.assertFalse(proxy.public_address(value))

    def test_real_tls_client_hello_sni(self):
        for host in ['en.wikibooks.org','example.com']:
            incoming,outgoing=ssl.MemoryBIO(),ssl.MemoryBIO()
            client=ssl.create_default_context().wrap_bio(incoming,outgoing,server_hostname=host)
            with self.assertRaises(ssl.SSLWantReadError):
                client.do_handshake()
            self.assertEqual(proxy.tls_server_name(outgoing.read()),host)
        for data in [b'',b'GET / HTTP/1.1\r\n',b'\x16\x03\x01\xff\xff']:
            with self.assertRaises(ValueError):
                proxy.tls_server_name(data)

    def test_denied_connect_never_resolves_or_connects(self):
        class Client:
            data=bytearray(b'CONNECT 169.254.169.254:443 HTTP/1.1\r\n\r\n')
            sent=b''
            def settimeout(self,value): pass
            def recv(self,count):
                result=bytes(self.data[:count]); del self.data[:count]; return result
            def sendall(self,data): self.sent+=data
        client=Client()
        with patch.object(proxy,'upstream_connection') as upstream:
            proxy.Handler(client,None,None)
        upstream.assert_not_called()
        self.assertIn(b'403 Forbidden',client.sent)

    def test_allowed_connect_with_wrong_tls_sni_never_connects(self):
        incoming,outgoing=ssl.MemoryBIO(),ssl.MemoryBIO()
        client_tls=ssl.create_default_context().wrap_bio(incoming,outgoing,server_hostname='example.com')
        with self.assertRaises(ssl.SSLWantReadError):
            client_tls.do_handshake()
        class Client:
            data=bytearray(b'CONNECT en.wikibooks.org:443 HTTP/1.1\r\n\r\n'+outgoing.read())
            def settimeout(self,value): pass
            def recv(self,count):
                result=bytes(self.data[:count]); del self.data[:count]; return result
            def sendall(self,data): pass
        with patch.object(proxy,'upstream_connection') as upstream:
            proxy.Handler(Client(),None,None)
        upstream.assert_not_called()

    def test_network_none_and_readonly_private_volume(self):
        command=docker_command('image','name',300,'private-test-socket')
        self.assertEqual(command[command.index('--network')+1],'none')
        mount=command[command.index('--mount')+1]
        self.assertIn('type=volume',mount)
        self.assertIn('readonly',mount)
        self.assertNotIn('type=bind',str(command))
        self.assertNotIn('API_KEY',str(command))

    def test_optional_policy_changes_identity_and_runtime(self):
        old=Config()
        self.assertIsInstance(runtime_descriptor(old),list)
        enabled=dataclasses.replace(old,evaluator_egress_proxy_image='sha256:'+'a'*64)
        self.assertNotEqual(old.identity(),enabled.identity())
        self.assertEqual(runtime_descriptor(enabled)['policy']['hosts'],['en.wikibooks.org'])

    def test_proxy_failure_cleans_up_owned_resources(self):
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=1,stdout='',stderr='setup failed')
        with patch('crosscode.egress.subprocess.run',side_effect=run):
            with self.assertRaises(EgressSetupError):
                with restricted_broker('image','crosscode-test-owned',30):
                    self.fail('Failed proxy setup must never expose evaluator socket')
        self.assertEqual(calls[-2],['docker','rm','-f','crosscode-test-owned-egress'])
        self.assertEqual(calls[-1],['docker','volume','rm','-f','crosscode-test-owned-socket'])


if __name__=='__main__':
    unittest.main()
