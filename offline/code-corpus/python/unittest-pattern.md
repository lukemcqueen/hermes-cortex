---
language: python
tags: [test]
title: Unit Testing with unittest
description: Standard unittest patterns: setup, assertions, mocks, and parameterized.
source: pattern
---

```python
import unittest
from unittest.mock import Mock, patch

class TestMyModule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Run once before all tests
        pass

    def setUp(self):
        # Run before each test
        self.data = {'key': 'value'}

    def test_basic_assertions(self):
        self.assertEqual(2 + 2, 4)
        self.assertTrue(True)
        self.assertIn('key', self.data)
        self.assertIsNone(None)
        self.assertRaises(ValueError, int, 'not_a_number')

    @patch('module.external_api')
    def test_with_mock(self, mock_api):
        mock_api.return_value = {'status': 'ok'}
        result = my_function()
        mock_api.assert_called_once_with(expected_arg)

    def test_exception_handling(self):
        with self.assertRaises(ValueError) as ctx:
            parse_bad_input('')
        self.assertIn('invalid', str(ctx.exception))

if __name__ == '__main__':
    unittest.main()
```
