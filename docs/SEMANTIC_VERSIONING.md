# Semantic Versioning

This document explains the automated semantic versioning system used in this project.

## Overview

This project uses automated semantic versioning based on commit message conventions. The versioning system is implemented through GitHub Actions workflows that analyze commit messages to determine the appropriate version bump.

## Version Bump Rules

- **Major (`X`.0.0)**: Breaking changes
  - Keywords: `BREAKING CHANGE:`, `breaking:`, `!:`, `major:`
  - Example: `refactor!: redesign API endpoints`

- **Minor (X.`Y`.0)**: New features
  - Keywords: `feat:`, `feature:`, `add:`, `minor:`
  - Example: `feat: add user authentication`

- **Patch (X.Y.`Z`)**: Bug fixes and other changes
  - Keywords: Any other commit message
  - Example: `fix: resolve login timeout`

## How It Works

1. **Trigger**: When PRs are merged to `main` or `dev` branches, or manually via `workflow_dispatch`
2. **Version calculation**: Analyzes commit messages from the current PR/push to determine bump type
3. **Version increment**: Increments from the latest Git tag (or starts from `0.1.1` if no tags exist)
4. **Container images**: Builds and pushes images to `quay.io/ecosystem-appeng/{IMAGE_PREFIX}-{component}:{version}` (e.g., `quay.io/ecosystem-appeng/aiobs-metrics-api:1.2.3`)
5. **Auto-update**: Updates version in:
   - `deploy/helm/metrics-api/values.yaml`
   - `deploy/helm/ui/values.yaml` 
   - `deploy/helm/alerting/values.yaml`
   - `Makefile` VERSION variable
6. **Git commit**: Commits version updates with `[skip ci]` to prevent infinite loops

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
2. **Finds latest tag**: Uses `git describe --tags --abbrev=0` or defaults to `0.1.1`
3. **Analyzes commits**: Scans commit messages for version bump keywords
4. **Calculates new version**: Increments major, minor, or patch based on findings
5. **Builds containers**: Creates container images with the new version tag
6. **Updates files**: Automatically updates version references across the project

### Version Detection Logic

```bash
# Major version detection
if echo "$COMMITS" | grep -qiE "(BREAKING CHANGE:?|breaking:|\!:|major:)"; then
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0

# Minor version detection  
elif echo "$COMMITS" | grep -qiE "(feat:|feature:|add:|minor:)"; then
    MINOR=$((MINOR + 1))
    PATCH=0

# Patch version (default)
else
    PATCH=$((PATCH + 1))
fi
```

### Files Updated Automatically

When a new version is calculated, these files are automatically updated:

1. **Helm Charts:**
   - `deploy/helm/metrics-api/values.yaml`
   - `deploy/helm/ui/values.yaml`
   - `deploy/helm/alerting/values.yaml`

2. **Build Configuration:**
   - `Makefile` (VERSION variable)

3. **Git Tags:**
   - New version tag is created automatically

### Container Image Naming

Images are built and pushed with semantic version tags:

- `quay.io/ecosystem-appeng/aiobs-metrics-api:1.2.3`
- `quay.io/ecosystem-appeng/aiobs-metrics-ui:1.2.3`
- `quay.io/ecosystem-appeng/aiobs-metrics-alerting:1.2.3`

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
2. **Version not updating**: Ensure PR is merged to `main` or `dev`
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