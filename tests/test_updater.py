from __future__ import annotations

import unittest

from gitkrakit.client_config import ClientConfig
from gitkrakit.ui.updater import UpdaterController, progress_percent


class UpdaterTests(unittest.TestCase):
    def test_normalizes_progress_values(self):
        self.assertEqual(progress_percent({"percent_complete": 42.9}), 42)
        self.assertEqual(progress_percent({"downloaded": 3, "total": 4}), 75)
        self.assertEqual(progress_percent({"percent_complete": 120}), 100)
        self.assertEqual(progress_percent({"percent_complete": -4}), 0)
        self.assertEqual(progress_percent({"percent_complete": "invalid"}), 0)

    def test_release_configuration_has_public_key_and_stable_url(self):
        self.assertEqual(ClientConfig.APP_NAME, "GitKrakit")
        self.assertEqual(ClientConfig.COMPANY_NAME, "Robnelito")
        self.assertTrue(ClientConfig.PUBLIC_KEY)
        self.assertEqual(
            ClientConfig.UPDATE_URLS,
            [
                "https://github.com/Robnelito/GitKrakit/"
                "releases/download/latest-updates/"
            ],
        )

    def test_source_mode_reports_updater_as_unavailable_without_network(self):
        controller = UpdaterController()
        reports = []
        controller.unavailable.connect(reports.append)

        self.assertTrue(controller.check(manual=True))
        self.assertEqual(reports, [True])

    def test_failed_download_cleans_partial_payload_and_allows_retry(self):
        class InterruptedUpdate:
            cleaned = False

            def download(self):
                raise OSError("network interrupted")

            def cleanup(self):
                self.cleaned = True

        update = InterruptedUpdate()
        controller = UpdaterController()
        controller._app_update = update
        controller._downloading = True
        failures = []
        controller.download_failed.connect(failures.append)

        controller._download_worker()

        self.assertTrue(update.cleaned)
        self.assertFalse(controller._downloading)
        self.assertEqual(failures, ["network interrupted"])


if __name__ == "__main__":
    unittest.main()
