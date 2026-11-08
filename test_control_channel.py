import unittest,tempfile,time
from pathlib import Path
from control_channel import send,collect,alive,write_json

class ControlTests(unittest.TestCase):
    def test_command_roundtrip_and_consumed_once(self):
        with tempfile.TemporaryDirectory() as d:
            identifier=send(d,'pause');commands=collect(d)
            self.assertEqual(commands[0]['id'],identifier);self.assertEqual(commands[0]['action'],'pause');self.assertEqual(collect(d),[])
    def test_disallows_arbitrary_command(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):send(d,'run arbitrary code')
    def test_stale_command_not_executed(self):
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d)/'control'/'old.json',dict(action='resume',time=time.time()-60));self.assertEqual(collect(d),[])
    def test_heartbeat_fresh_and_stopped(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'background-heartbeat.json'
            write_json(p,dict(alive=True,time=time.time()));self.assertTrue(alive(d))
            write_json(p,dict(alive=False,time=time.time()));self.assertFalse(alive(d))
    def test_locked_status_file_cannot_interrupt_game(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            with patch('control_channel.os.replace',side_effect=PermissionError('reader holds file')):
                self.assertFalse(write_json(Path(d)/'status.json',{'state':'running'},best_effort=True))
