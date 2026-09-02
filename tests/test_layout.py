import unittest

import server


class HeaderLayoutTests(unittest.TestCase):
    def test_training_title_is_inside_header_between_brand_and_navigation(self):
        response = server.app.test_client().get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        header_start = html.index('<header class="site-header">')
        header_end = html.index("</header>", header_start)
        header = html[header_start:header_end]

        brand_position = header.index('class="brand"')
        title_position = header.index('class="header-training-title"')
        navigation_position = header.index('class="nav-links"')

        self.assertLess(brand_position, title_position)
        self.assertLess(title_position, navigation_position)
        self.assertIn("LỚP TẬP HUẤN BỒI DƯỠNG KIẾN THỨC", header)
        self.assertIn("CÔNG NGHỆ THÔNG TIN, TRÍ TUỆ NHÂN TẠO", header)
        self.assertNotIn('class="training-banner"', html)


if __name__ == "__main__":
    unittest.main()
