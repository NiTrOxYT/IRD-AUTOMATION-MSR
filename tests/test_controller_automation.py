import unittest
from unittest.mock import patch, MagicMock
from app.main import app
from app.controller_automation.models import (
    ControllerCloneRequest,
    TestConnectionRequest,
    ControllerStep,
    ControllerRunStatus
)
from app.controller_automation.ssh_runner import MultiHopSSHRunner
from app.controller_automation.workflow_runner import ControllerWorkflowRunner
from app.database.db import (
    create_controller_run,
    update_controller_run,
    get_controller_run_by_uuid,
    get_controller_runs_history,
    get_all_controller_settings,
    save_controller_settings
)


class TestControllerModels(unittest.TestCase):
    def test_target_ip_property_for_existing_controller(self):
        req = ControllerCloneRequest(
            site_ip="14.142.185.130",
            current_room_no="201",
            current_room_ip="10.172.1.201",
            similar_room_no="202",
            similar_room_ip="10.172.1.202",
            is_new_controller=False
        )
        self.assertEqual(req.target_ip, "10.172.1.201")

    def test_target_ip_property_for_new_controller(self):
        req = ControllerCloneRequest(
            site_ip="14.142.185.130",
            current_room_no="305",
            current_room_ip="10.172.3.5",
            similar_room_no="304",
            similar_room_ip="10.172.3.4",
            is_new_controller=True
        )
        self.assertEqual(req.target_ip, "10.172.100.100")

    def test_test_connection_request_target_ip(self):
        req = TestConnectionRequest(
            site_ip="14.142.185.130",
            current_room_ip="10.172.5.10",
            similar_room_ip="10.172.5.11",
            is_new_controller=True
        )
        self.assertEqual(req.target_ip, "10.172.100.100")


class TestControllerDatabase(unittest.TestCase):
    def test_settings_get_and_save(self):
        settings = get_all_controller_settings()
        self.assertIn("jump_host", settings)
        self.assertEqual(settings["jump_host"], "111.93.205.187")
        self.assertIn("candidate_passwords", settings)

        save_controller_settings({"jump_port": "2222"})
        updated = get_all_controller_settings()
        self.assertEqual(updated["jump_port"], "2222")

        # Restore default
        save_controller_settings({"jump_port": "22"})

    def test_run_crud(self):
        import uuid
        test_uuid = f"test_ctrl_{uuid.uuid4().hex[:10]}"
        run_data = {
            "run_uuid": test_uuid,
            "site_name": "Test Site ITC",
            "site_ip": "10.0.0.1",
            "current_room_no": "101",
            "current_room_ip": "10.172.1.101",
            "similar_room_no": "102",
            "similar_room_ip": "10.172.1.102",
            "is_new_controller": True,
            "target_ip": "10.172.100.100",
            "status": "RUNNING",
            "steps": [{"id": "hop_check", "status": "RUNNING"}],
            "logs": [{"timestamp": "12:00:00", "level": "INFO", "message": "Test"}]
        }
        run_id = create_controller_run(run_data)
        self.assertGreater(run_id, 0)

        record = get_controller_run_by_uuid(test_uuid)
        self.assertIsNotNone(record)
        self.assertEqual(record["site_name"], "Test Site ITC")
        self.assertEqual(record["is_new_controller"], 1)

        update_controller_run(test_uuid, {
            "status": "SUCCESS",
            "discovered_password": "msr123",
            "duration_seconds": 15.5
        })

        updated = get_controller_run_by_uuid(test_uuid)
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["discovered_password"], "msr123")
        self.assertEqual(updated["duration_seconds"], 15.5)


class TestControllerSSHRunner(unittest.TestCase):
    @patch("subprocess.run")
    def test_run_on_jump_base64_wrapping(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="JUMP_OK\n", stderr="")
        runner = MultiHopSSHRunner(jump_host="111.93.205.187", jump_user="sourik", jump_pass="s0urik@@")
        code, out, err = runner.run_on_jump("echo test_hello")

        self.assertEqual(code, 0)
        self.assertIn("JUMP_OK", out)
        # Verify plink args were called
        args = mock_subproc.call_args[0][0]
        self.assertEqual(args[1], "-batch")
        self.assertEqual(args[3], "-P")
        self.assertIn("-l", args)
        self.assertIn("-pw", args)
        self.assertIn("echo", args[-1])
        self.assertIn("base64 -d | bash", args[-1])

    @patch("subprocess.run")
    def test_discover_controller_password_first_match(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="CONTROLLER_AUTH_SUCCESS\n", stderr="")
        runner = MultiHopSSHRunner()
        pwd, msg = runner.discover_controller_password(
            "10.0.0.1", 22, "support", "pwd", "10.172.100.100", ["msr123", "msr@123"]
        )
        self.assertEqual(pwd, "msr123")
        self.assertIn("Authenticated successfully", msg)

    @patch("subprocess.run")
    def test_discover_controller_password_second_match(self, mock_subproc):
        # First call fails, second call succeeds
        mock_subproc.side_effect = [
            MagicMock(returncode=1, stdout="Permission denied\n", stderr=""),
            MagicMock(returncode=0, stdout="CONTROLLER_AUTH_SUCCESS\n", stderr="")
        ]
        runner = MultiHopSSHRunner()
        pwd, msg = runner.discover_controller_password(
            "10.0.0.1", 22, "support", "pwd", "10.172.100.100", ["msr123", "msr@123"]
        )
        self.assertEqual(pwd, "msr@123")


class TestControllerWorkflowRunner(unittest.TestCase):
    @patch.object(MultiHopSSHRunner, "test_jump_connection", return_value=(True, "Jump OK"))
    @patch.object(MultiHopSSHRunner, "test_site_connection", return_value=(True, "Site OK"))
    @patch.object(MultiHopSSHRunner, "discover_controller_password", return_value=("msr123", "Target OK"))
    def test_test_connection_success(self, mock_disc, mock_site, mock_jump):
        runner = ControllerWorkflowRunner()
        req = TestConnectionRequest(
            site_ip="10.0.0.1",
            current_room_ip="10.172.1.101",
            similar_room_ip="10.172.1.102",
            is_new_controller=False
        )
        res = runner.test_connection(req)
        self.assertTrue(res.success)
        self.assertTrue(res.jump_status["connected"])
        self.assertTrue(res.site_status["connected"])
        self.assertTrue(res.target_controller_status["connected"])
        self.assertTrue(res.similar_controller_status["connected"])


if __name__ == "__main__":
    unittest.main()
