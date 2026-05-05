import os
from pydantic_settings import BaseSettings

class MySettings(BaseSettings):
    github_token: str = ""
    class Config:
        env_file = ".env"

if "GITHUB_TOKEN" not in os.environ:
    os.environ["GITHUB_TOKEN"] = ""  # Simulate parent uvicorn process caching an empty string

s = MySettings()
print(f"Token is: '{s.github_token}'")
