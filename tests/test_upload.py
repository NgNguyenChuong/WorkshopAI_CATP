import io
import json
import tempfile
import unittest
from pathlib import Path

import server


class UploadPageTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_submissions_dir = server.SUBMISSIONS_DIR
        server.SUBMISSIONS_DIR = Path(self.temp_directory.name)
        server.app.config.update(TESTING=True)
        self.client = server.app.test_client()

    def tearDown(self):
        server.SUBMISSIONS_DIR = self.original_submissions_dir
        self.temp_directory.cleanup()

    def post_upload(self, files, student_name="Nguyễn Văn An", group="Nhóm 1"):
        return self.client.post(
            "/upload",
            data={
                "student_name": student_name,
                "group": group,
                "submission_files": [
                    (io.BytesIO(content), filename) for filename, content in files
                ],
            },
            content_type="multipart/form-data",
        )

    def submission_directories(self):
        return sorted(path for path in server.SUBMISSIONS_DIR.iterdir() if path.is_dir())

    def test_form_only_asks_for_name_group_and_multiple_files(self):
        response = self.client.get("/upload")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('name="student_name"', html)
        self.assertIn('name="group"', html)
        self.assertIn('name="submission_files"', html)
        self.assertIn(" multiple", html)
        self.assertNotIn('name="student_id"', html)
        self.assertNotIn('name="assignment"', html)

    def test_accepts_five_files_of_different_types(self):
        response = self.post_upload(
            [
                ("photo.jpg", b"image"),
                ("clip.mp4", b"video"),
                ("notes.docx", b"document"),
                ("archive.zip", b"archive"),
                ("data.bin", b"binary"),
            ]
        )

        self.assertEqual(response.status_code, 200)
        directories = self.submission_directories()
        self.assertEqual([path.name for path in directories], ["001_Nguyen_Van_An"])
        self.assertEqual(
            sorted(path.name for path in directories[0].iterdir()),
            [
                "archive.zip",
                "clip.mp4",
                "data.bin",
                "metadata.json",
                "notes.docx",
                "photo.jpg",
            ],
        )

        metadata = json.loads(
            (directories[0] / "metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["student_number"], 1)
        self.assertEqual(metadata["group"], "Nhóm 1")
        self.assertEqual(len(metadata["uploads"]), 1)

    def test_repeat_upload_reuses_folder_and_does_not_overwrite(self):
        first = self.post_upload([("photo.jpg", b"first")])
        second = self.post_upload(
            [("photo.jpg", b"second")],
            student_name="  NGUYỄN   VĂN AN  ",
            group="nhóm 1",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        directories = self.submission_directories()
        self.assertEqual(len(directories), 1)
        self.assertEqual((directories[0] / "photo.jpg").read_bytes(), b"first")
        self.assertEqual((directories[0] / "photo_2.jpg").read_bytes(), b"second")

        metadata = json.loads(
            (directories[0] / "metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(metadata["uploads"]), 2)

    def test_rejects_more_than_five_files(self):
        response = self.post_upload(
            [(f"file-{index}.txt", b"content") for index in range(6)]
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.submission_directories(), [])

    def test_same_name_in_another_group_gets_another_number(self):
        first = self.post_upload([("one.txt", b"one")], group="Nhóm 1")
        second = self.post_upload([("two.txt", b"two")], group="Nhóm 2")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            [path.name for path in self.submission_directories()],
            ["001_Nguyen_Van_An", "002_Nguyen_Van_An"],
        )


if __name__ == "__main__":
    unittest.main()
