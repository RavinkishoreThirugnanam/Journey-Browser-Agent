from uuid import uuid4

from schemas.test_script_schema import TestScript


def generate_test_scripts(test_cases: list[dict]) -> list[TestScript]:
    scripts: list[TestScript] = []
    for test_case in test_cases:
        scripts.append(
            TestScript(
                script_id=str(uuid4()),
                test_case_id=test_case["test_case_id"],
                feature_file=f"Feature: {test_case['title']}\n  Scenario: Execute journey\n    Given the application is reachable\n    When the user follows the journey\n    Then the expected results are observed\n",
                javascript_file=f"describe('{test_case['title']}', () => {{ test('journey flow', async () => {{ /* mock automation */ }}); }});",
            )
        )
    return scripts
