# Semantic Versioning

This document explains the automated semantic versioning system used in this project.

## Overview

This project uses automated semantic versioning based on PR labels, PR titles, and commit message conventions. The versioning system is implemented through GitHub Actions workflows that analyze PR information and commit messages in order of priority to determine the appropriate version bump.

## Version Bump Rules

The workflow determines version bumps in this **order of priority**:

1. **PR Labels** (highest priority)
2. **PR Title** (medium priority) 
3. **Commit Messages** (fallback)

### Version Types

- **Major (`X`.0.0)**: Breaking changes
  - Keywords: `BREAKING CHANGE:`, `BREAKING CHANGE` (colon optional), `breaking:`, `!:`, `major:`
  - Example PR label: `major:`, `breaking:`, `!:`
  - Example PR title: `refactor!: redesign API endpoints`

- **Minor (X.`Y`.0)**: New features
  - Keywords: `feat:`, `feature:`, `add:`, `minor:`
  - Example PR label: `feature:`, `feat:`, `add:`, `minor:`
  - Example PR title: `feat: add user authentication`

- **Patch (X.Y.`Z`)**: Bug fixes and other changes
  - Keywords: `patch`, `bugfix`, `fix`, `documentation` (no colons)
  - Example PR label: `patch`, `bugfix`, `fix`, `documentation`
  - Example commit message: `fix: resolve login timeout`

## How It Works

1. **Trigger**: When PRs are merged to `main` or `dev` branches, or manually via `workflow_dispatch`
   - **Version file updates**: Only occur when pushing to non-main branches
   - **Container builds**: Occur for all branches
2. **Version calculation**: Analyzes PR labels and PR title **first**, then falls back to commit messages to determine bump type
3. **Version increment**: Increments from the current version in Makefile (or starts from `0.1.1` if no version exists)
4. **Container images**: Builds and pushes images to `quay.io/ecosystem-appeng/{IMAGE_PREFIX}-{component}:{version}` (e.g., `quay.io/ecosystem-appeng/aiobs-metrics-ui:1.2.3`)
5. **Auto-update**: Updates version files **only when pushing to non-main branches**:
   - `deploy/helm/ui/values.yaml` 
   - `deploy/helm/alerting/values.yaml`
   - `deploy/helm/mcp-server/values.yaml`
   - `Makefile` VERSION variable
6. **Git commit**: Commits version updates automatically to the current branch

## Version Bump Examples

### Using PR Labels (Recommended)

The easiest way to control versioning is by adding labels to your pull request:

**Major Version Bump:**
- Add label: `major:`, `breaking:`, `!:`, or `BREAKING CHANGE` (with or without colon)
- Example: PR with label `breaking:` → Major version bump

**Minor Version Bump:**
- Add label: `feat:`, `feature:`, `add:`, or `minor:`  
- Example: PR with label `feature:` → Minor version bump

**Patch Version Bump:**
- Add label: `patch`, `bugfix`, `fix`, or `documentation` (no colons)
- Example: PR with label `bugfix` → Patch version bump

### Using PR Titles

If no matching labels are found, the workflow checks the PR title:

**Major Version Bump:**
```
feat!: redesign authentication system
refactor!: change API structure  
major: remove deprecated endpoints
```

**Minor Version Bump:**
```
feat: add dark mode support
feature: implement user profiles
add: support for GPU monitoring
```

**Patch Version Bump:**
```
fix: resolve memory leak
docs: update installation guide
Any title without specific keywords
```

## Commit Message Examples

### Major Version Bump (`X`.0.0)

Breaking changes that require major version bump:

```bash
# Using "BREAKING CHANGE:" in commit message body
git commit -m "refactor: change API structure

BREAKING CHANGE: API endpoints restructured"

# Using "!" in commit type
git commit -m "refactor!: change API structure"

# Using "major:" keyword
git commit -m "major: remove deprecated features"
```

### Minor Version Bump (X.`Y`.0)

New features that require minor version bump:

```bash
# New feature addition
git commit -m "feat: add metrics dashboard"

# Using "feature:" keyword
git commit -m "feature: implement user authentication"

# Using "add:" keyword
git commit -m "add: support for new GPU metrics"

# Using "minor:" keyword
git commit -m "minor: enhance UI with new charts"
```

### Patch Version Bump (X.Y.`Z`)

Bug fixes and other changes that require patch version bump:

```bash
# Bug fix
git commit -m "fix: resolve memory leak in alerting"

# Documentation update
git commit -m "docs: update installation guide"

# Chore or maintenance
git commit -m "chore: update dependencies"

# Any commit without specific keywords
git commit -m "resolve memory leak in alerting"
```

## Implementation Details

### Build Workflow Analysis

The build workflow (`.github/workflows/build-and-push.yml`) performs these steps:

1. **Fetches commit history**: Gets full history to analyze commit messages
2. **Gets current version**: Reads VERSION from Makefile or defaults to `0.1.1`
3. **Analyzes PR information**: Checks PR labels and title first, then commit messages
4. **Calculates new version**: Increments major, minor, or patch based on priority order
5. **Builds containers**: Creates container images with the new version tag
6. **Updates files**: Automatically updates version references across the project

### Version Detection Logic

```bash
# Priority 1: Check PR labels first
if [ -n "$PR_LABELS" ] && echo "$PR_LABELS" | grep -qiE "$MAJOR_PATTERN"; then
    MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0
elif [ -n "$PR_LABELS" ] && echo "$PR_LABELS" | grep -qiE "$MINOR_PATTERN"; then
    MINOR=$((MINOR + 1)); PATCH=0
elif [ -n "$PR_LABELS" ] && echo "$PR_LABELS" | grep -qiE "$PATCH_PATTERN"; then
    PATCH=$((PATCH + 1))

# Priority 2: Check PR title
elif [ -n "$PR_TITLE" ] && echo "$PR_TITLE" | grep -qiE "$MAJOR_PATTERN"; then
    MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0
elif [ -n "$PR_TITLE" ] && echo "$PR_TITLE" | grep -qiE "$MINOR_PATTERN"; then
    MINOR=$((MINOR + 1)); PATCH=0

# Priority 3: Fall back to commit message analysis
elif echo "$COMMITS" | grep -qiE "$MAJOR_PATTERN"; then
    MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0
elif echo "$COMMITS" | grep -qiE "$MINOR_PATTERN"; then
    MINOR=$((MINOR + 1)); PATCH=0
else
    PATCH=$((PATCH + 1))  # Default patch bump
fi
```

### Files Updated Automatically

When a new version is calculated and pushing to a non-main branch, these files are automatically updated:

1. **Helm Charts:**
   - `deploy/helm/ui/values.yaml`
   - `deploy/helm/alerting/values.yaml`
   - `deploy/helm/mcp-server/values.yaml`

2. **Build Configuration:**
   - `Makefile` (VERSION variable)

**Note**: _Version file updates only occur when pushing to non-main branches. When pushing to `main` branch, container images are built with the calculated version but version files remain unchanged._

### Container Image Naming

Images are built and pushed with semantic version tags:

- `quay.io/ecosystem-appeng/aiobs-metrics-ui:1.2.3`
- `quay.io/ecosystem-appeng/aiobs-metrics-alerting:1.2.3`
- `quay.io/ecosystem-appeng/aiobs-mcp-server:1.2.3`

## Best Practices

### Commit Message Guidelines

1. **Use conventional commits**: Follow the `type: description` format
2. **Be descriptive**: Clearly describe what changed and why
3. **Use correct keywords**: Choose the right keyword for the intended version bump
4. **Breaking changes**: Always use `BREAKING CHANGE:` in the body for major bumps

### Example Workflow

```bash
# Feature development
git commit -m "feat: add dark mode toggle to settings"

# Bug fix
git commit -m "fix: resolve navigation menu alignment issue"

# Breaking change
git commit -m "refactor: change authentication API

BREAKING CHANGE: Authentication endpoints now require different headers"

# Documentation
git commit -m "docs: update API documentation for new endpoints"
```

### Version Planning

- **Patch releases**: Bug fixes, documentation updates, small improvements
- **Minor releases**: New features, enhancements that maintain compatibility
- **Major releases**: Breaking changes, API redesigns, major architectural changes

## Troubleshooting

### Common Issues

1. **Wrong version bump**: Check commit message keywords
2. **Version not updating**:
   - For non-main branches: Ensure PR is merged to the branch
   - For `main` branch: Version files are not auto-updated (uses existing versions)
3. **Build failures**: Check container registry permissions
4. **Git conflicts**: Resolve conflicts in version update commits

### Manual Version Override

If you need to manually set a version:

1. Create a git tag: `git tag 1.2.3`
2. Push the tag: `git push origin 1.2.3`
3. The next build will increment from this version

### Skipping CI

To prevent infinite loops, version update commits include `[skip ci]` which prevents them from triggering new builds.

## Configuration

### Environment Variables

The versioning system uses these configuration options:

- **DEFAULT_VERSION**: `0.1.1` (starting version if no tags exist)
- **REGISTRY**: `quay.io` (container registry)
- **ORG**: `ecosystem-appeng` (registry organization)
- **IMAGE_PREFIX**: `aiobs` (image name prefix for all containers)

### Customization

To modify versioning behavior, edit `.github/workflows/build-and-push.yml`:

- Change default starting version
- Modify keyword detection patterns
- Add new file update targets
- Customize container naming