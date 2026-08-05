def generate_github_actions_yaml(path=".github/workflows/eval.yml"):
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("name: OpenHarness Eval\non: [push]\njobs:\n  eval:\n    runs-on: ubuntu-latest\n    steps:\n    - uses: actions/checkout@v2\n    - run: harness run")
