with open("backend/agent/github_client.py", "r") as f:
    text = f.read()

# Patches headers
old_headers = """    @property
    def headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers"""

new_headers = """    @property
    def headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            logger.warning("No GitHub token provided to GitHubClient!")
        # Debug print
        print(f"DEBUG: Using headers: {list(headers.keys())}")
        return headers"""

text = text.replace(old_headers, new_headers)

with open("backend/agent/github_client.py", "w") as f:
    f.write(text)
