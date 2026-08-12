from fastapi import FastAPI


def test_app_bootstraps_with_expected_metadata(app: FastAPI) -> None:
    assert app.title == "Exam Prep Agent Test"
    assert app.version == "0.1.0"
