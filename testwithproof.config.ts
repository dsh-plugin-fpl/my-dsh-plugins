export default {
  name: "DSH independent services: managed setup candidate",
  root: ".",
  executors: {
    packages: { type: "pytest", command: "dsh-core/.runtime/worker-venv/bin/python", args: ["-m", "pytest", "tests/integration/test_managed_packages.py", "-q"], dependencies: "real", timeoutMs: 120000 },
    hosts: { type: "pytest", command: "dsh-core/.runtime/worker-venv/bin/python", args: ["-m", "pytest", "tests/integration/test_managed_hosts.py", "-q"], dependencies: "real", timeoutMs: 1800000 },
    regressions: { type: "pytest", command: "dsh-core/.runtime/worker-venv/bin/python", args: ["-m", "pytest", "tests/integration/test_managed_regressions.py", "-q"], dependencies: "mocked", timeoutMs: 600000 },
    workflows: { type: "pytest", command: "dsh-core/.runtime/worker-venv/bin/python", args: ["-m", "pytest", "tests/integration/test_managed_workflows.py", "-q"], dependencies: "mocked", timeoutMs: 600000 },
  },
};
