class Settings:
    github_token = "ENV_TOKEN"
settings = Settings()

class GitHubClient:
    def __init__(self, token=None):
        self.token = token or settings.github_token

class ReviewConfig:
    def __init__(self, raw: dict):
        self.github_token = raw.get("github_token")

raw = {} # Similar to UI request without token
config = ReviewConfig(raw)
gh = GitHubClient(token=config.github_token)

print(f"Config token: {config.github_token}")
print(f"GH Client token: {gh.token}")
