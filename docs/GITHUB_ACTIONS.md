# GitHub Actions CI/CD

This document provides detailed information about the GitHub Actions workflows used in this project for automated CI/CD.

## Overview

The project uses 5 GitHub Actions workflows with the following execution order and dependencies:

### PR Review Workflows (Run in Parallel)
1. **Run Tests** (`.github/workflows/run_tests.yml`)
   - **Trigger:** Pull request events (opened, synchronize, reopened) and pushes to `main`/`dev`
   - **Purpose:** Runs the Python test suite with coverage reporting during PR review
   - **Dependencies:** None - runs independently during PR review

2. **Rebase Check** (`.github/workflows/rebase-check.yml`)
   - **Trigger:** Pull request events (opened, synchronize, reopened)
   - **Purpose:** Ensures PRs are up-to-date with base branch before merge
   - **Actions:** Posts rebase instructions if PR is behind, fails the check
   - **Dependencies:** None - runs independently during PR review

### Post-Merge Workflows (Sequential Chain)

3. **Build and Push** (`.github/workflows/build-and-push.yml`)
   - **Trigger:** PRs merged to `main` or `dev` branches, manual dispatch
   - **Purpose:** Builds and pushes container images with semantic versioning
   - **Actions:** 
     - Analyzes commit messages for version bumps
     - Builds 3 container images (using `IMAGE_PREFIX`-component naming):
       - aiobs-metrics-api
       - aiobs-metrics-ui
       - aiobs-metrics-alerting
     - Updates Helm charts and Makefile with new version
   - **Image naming:** Semantic versions (e.g., `0.1.2`, `1.0.0`)
   - **Dependencies:** None - runs after merge

4. **Deploy to OpenShift** (`.github/workflows/deploy.yml`)
   - **Trigger:** Automatic after successful Build workflow, manual dispatch
   - **Purpose:** Deploys application to OpenShift cluster
   - **Dependencies:** ✅ **Requires Build and Push workflow success**

5. **Undeploy from OpenShift** (`.github/workflows/undeploy.yml`)
   - **Trigger:** Automatic after successful Deploy workflow, manual dispatch
   - **Purpose:** Cleans up deployments after testing period (configurable delay)
   - **Dependencies:** ✅ **Requires Deploy workflow success**

### Workflow Dependency Diagram
```
PR Created/Updated
├── Run Tests (parallel) ✅
└── Rebase Check (parallel) ✅

PR Merged to main/dev
└── Build and Push ✅
    └── Deploy to OpenShift ✅
        └── Undeploy from OpenShift (after delay) ✅
```

## OpenShift Service Account Setup

Before using the GitHub Actions workflows, you need to create a service account with appropriate permissions in your OpenShift cluster.

### Prerequisites
- OpenShift CLI (`oc`) installed and configured
- `envsubst` utility (usually pre-installed on most systems)
- Cluster administrator access to OpenShift

### Setup Instructions

1. **Login to OpenShift:**
   ```bash
   oc login <your-openshift-server-url>
   ```

2. **Run the setup script:**
   ```bash
   # Initial setup and token extraction
   ./scripts/ocp-setup.sh -s -t -n <your-namespace>
   
   # Or run steps separately:
   ./scripts/ocp-setup.sh -s -n <your-namespace>    # Setup only
   ./scripts/ocp-setup.sh -t -n <your-namespace>    # Extract token only
   ```

### What the Script Does

The `scripts/ocp-setup.sh` script performs the following actions:

1. **Creates namespace** (if it doesn't exist)
2. **Creates service account** `github-actions` in the specified namespace
3. **Grants permissions:**
   - `edit` role in the target namespace
   - `cluster-admin` role for deployment operations
   - Special permissions for monitoring, alerting, and observability components
4. **Creates token secret** for authentication
5. **Extracts the token** and displays configuration values

### Permissions Granted

The service account receives these permissions:
- **Namespace-level**: Edit permissions for deploying applications
- **Cluster-level**: Admin permissions for creating cluster resources
- **Monitoring**: Access to Prometheus, AlertManager, and monitoring components
- **Observability**: Access to Tempo, OpenTelemetry, and tracing components

### Script Options

```bash
Usage: ./scripts/ocp-setup.sh [OPTIONS]

Options:
  -n/-N NAMESPACE          Target namespace (required)
  -s/-S                    Perform initial setup (create SA and grant permissions)
  -t/-T                    Extract token only
  -h                       Display help message

Examples:
  ./scripts/ocp-setup.sh -s -n my-namespace        # Initial setup
  ./scripts/ocp-setup.sh -T -N my-namespace        # Extract token only
  ./scripts/ocp-setup.sh -S -T -n my-namespace     # Setup and extract token
```

## Required Repository Secrets

After running the setup script, configure these secrets in your GitHub repository settings:

| Secret Name | Description | How to Obtain | Required For |
|-------------|-------------|---------------|--------------|
| `OPENSHIFT_SERVER` | OpenShift cluster API server URL | Output from setup script or `oc whoami --show-server` | Deploy/Undeploy workflows |
| `OPENSHIFT_TOKEN` | OpenShift service account token | Output from setup script (`-t` option) | Deploy/Undeploy workflows |
| `HUGGINGFACE_API_KEY` | Hugging Face API token for model access | [Create at huggingface.co](https://huggingface.co/settings/tokens) | Deploy workflow |
| `QUAY_USERNAME` | Quay.io registry username | Your Quay.io account username | Build and Push workflow |
| `QUAY_PASSWORD` | Quay.io registry password/token | Your Quay.io account password or [robot token](https://quay.io/organization/your-org?tab=robots) | Build and Push workflow |

## Workflow Configuration

**Deploy Workflow:**
- **Automatic trigger:** Runs after successful build workflow
- **Manual trigger:** Can specify custom namespace (default: `test-workflow-deploy`)
- **Force deploy option:** Deploy even if build workflow didn't run

**Undeploy Workflow:**
- **Automatic trigger:** Runs after successful deployment with configurable delay (default: 10 minutes)
- **Manual trigger:** Requires checking confirmation checkbox and specifying namespace
- **Configurable delay:** Set custom wait time before auto-cleanup
- **Safety features:** Can be cancelled during delay period, mandatory confirmation for manual runs

## Manual Workflow Execution

Most workflows run automatically, but some can be triggered manually:

### Automatic Workflows (No Manual Trigger)
- **Run Tests:** Triggered by PR events (opened, synchronize, reopened) and pushes to `main`/`dev`
- **Rebase Check:** Triggered by PR events (opened, synchronize, reopened)

### Manual Workflows
1. Go to **Actions** tab in your GitHub repository
2. Select the desired workflow
3. Click **Run workflow**
4. Fill in required parameters:

**Build and Push:**
- No parameters required - runs with default settings

**Deploy to OpenShift:**
- `namespace`: Target namespace (default: `test-workflow-deploy`)
- `force_deploy`: Deploy even if build workflow didn't run (default: `false`)

**Undeploy from OpenShift:**
- `namespace`: Target namespace (default: `test-workflow-deploy`)
- `confirm_uninstall`: Must check the confirmation checkbox for manual runs
- `delay_minutes`: Wait time before auto-uninstall (default: `10`)

## Workflow Variables

The workflows use these environment variables and inputs:

**Deploy Workflow:**
- `namespace`: Target OpenShift namespace (default: `test-workflow-deploy`)
- `force_deploy`: Boolean to force deployment (default: `false`)

**Undeploy Workflow:**
- `namespace`: Target OpenShift namespace (default: `test-workflow-deploy`)
- `confirm_uninstall`: Must check confirmation checkbox for manual runs (required: true, default: false)
- `delay_minutes`: Wait time before auto-uninstall (default: `10`)

## Troubleshooting

### Common Issues

1. **Failed OpenShift login:** Check `OPENSHIFT_SERVER` and `OPENSHIFT_TOKEN` secrets
2. **Permission denied:** Ensure service account has proper cluster permissions
3. **Build failures:** Check container registry credentials (`QUAY_USERNAME`/`QUAY_PASSWORD`)
4. **Deploy timeout:** Verify cluster resources and namespace quotas
5. **Missing HuggingFace models:** Ensure `HUGGINGFACE_API_KEY` is valid

### Debug Steps

1. Check workflow logs in GitHub Actions tab
2. Verify all required secrets are configured
3. Test OpenShift connectivity: `oc whoami`
4. Validate service account permissions: `oc auth can-i create pods --as=system:serviceaccount:<namespace>:github-actions`