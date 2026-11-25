import os
import sys
import time
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from companion_supervisor import CompanionSupervisor

class TestCompanionSupervisor(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.services_dir = os.path.join(self.test_dir, "services")
        self.logs_dir = os.path.join(self.test_dir, "logs")
        self.supervisor = CompanionSupervisor(self.services_dir, self.logs_dir)

    def tearDown(self):
        self.supervisor.shutdown_all()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_and_discover_service(self):
        code = "import time\nprint('Service alive!')\ntime.sleep(5)\n"
        res = self.supervisor.save_service(
            service_id="test_worker",
            name="Test Worker",
            description="A test background worker",
            code=code,
            auto_start=False,
            port=9999
        )
        self.assertTrue(res["success"])
        svcs = self.supervisor.discover_services()
        self.assertEqual(len(svcs), 1)
        self.assertEqual(svcs[0]["id"], "test_worker")
        self.assertEqual(svcs[0]["port"], 9999)
        self.assertEqual(svcs[0]["status"], "stopped")

    def test_start_and_stop_service(self):
        code = "import time, sys\nprint('Worker starting', flush=True)\nfor i in range(100):\n    print(f'Tick {i}', flush=True)\n    time.sleep(0.1)\n"
        self.supervisor.save_service("ticker", "Ticker", "Ticks", code)
        start_res = self.supervisor.start_service("ticker")
        self.assertTrue(start_res["success"])
        self.assertEqual(start_res["service"]["status"], "running")
        self.assertIsNotNone(start_res["service"]["pid"])

        # Wait a moment for ticks to log
        time.sleep(0.5)
        logs = self.supervisor.get_logs("ticker")
        self.assertTrue(len(logs) > 0)
        self.assertTrue(any("Worker starting" in l for l in logs))

        # Stop service
        stop_res = self.supervisor.stop_service("ticker")
        self.assertTrue(stop_res["success"])
        self.assertEqual(stop_res["service"]["status"], "stopped")

    def test_get_service_code(self):
        code = "print('Hello World')\n"
        self.supervisor.save_service("greeter", "Greeter", "", code)
        res = self.supervisor.get_service_code("greeter")
        self.assertTrue(res["success"])
        self.assertEqual(res["code"], code)

    def test_delete_service(self):
        code = "print('temp')\n"
        self.supervisor.save_service("temp_svc", "Temp", "", code)
        self.assertEqual(len(self.supervisor.discover_services()), 1)
        del_res = self.supervisor.delete_service("temp_svc")
        self.assertTrue(del_res["success"])
        self.assertEqual(len(self.supervisor.discover_services()), 0)

if __name__ == "__main__":
    unittest.main()
