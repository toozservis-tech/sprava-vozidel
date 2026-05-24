# GitHub Secret Scanning Setup Guide

## How to Enable GitHub Secret Scanning

### Step 1: Navigate to Repository Settings

1. Go to your GitHub repository: `https://github.com/toozservis-tech/TOOZHUB2`
2. Click on the **"Settings"** tab (located in the top menu bar of your repository)
3. In the left sidebar, scroll down and click on **"Security"**

### Step 2: Enable Secret Scanning

1. In the **"Security"** section, find **"Code security and analysis"**
2. Look for **"Secret scanning"** option
3. Click on **"Set up"** or **"Enable"** button next to "Secret scanning"
4. If you see a toggle switch, turn it **ON**

### Alternative Path (if above doesn't work):

1. Go to: `https://github.com/toozservis-tech/TOOZHUB2/settings/security_analysis`
2. Find **"Secret scanning"** section
3. Click **"Enable"** or toggle the switch to **ON**

### Step 3: Enable Push Protection (Recommended)

1. In the same **"Secret scanning"** section
2. Find **"Push protection"** option
3. Enable it by clicking **"Enable"** or toggling the switch **ON**
4. This will **prevent** commits with secrets from being pushed

### Step 4: Enable Dependabot Alerts (Also Recommended)

While you're in the Security settings:

1. Find **"Dependabot alerts"** section
2. Click **"Enable"** or toggle it **ON**
3. This will alert you about vulnerabilities in dependencies

### Step 5: Enable Dependabot Security Updates (Optional but Recommended)

1. Find **"Dependabot security updates"** section
2. Click **"Enable"** or toggle it **ON**
3. This will automatically create pull requests to fix security vulnerabilities

## What Secret Scanning Does

Once enabled, GitHub will:
- ✅ Automatically scan your repository for known secret patterns
- ✅ Alert you if secrets are detected in commits
- ✅ Block pushes if "Push protection" is enabled
- ✅ Scan both public and private repositories
- ✅ Check historical commits (retroactive scanning)

## Supported Secret Types

GitHub scans for secrets from:
- API keys (AWS, Google Cloud, Azure, etc.)
- Database credentials
- OAuth tokens
- Private keys
- Service account keys
- And many more (100+ secret types)

## Direct Links

**Repository Security Settings:**
```
https://github.com/toozservis-tech/TOOZHUB2/settings/security_analysis
```

**Repository Settings (General):**
```
https://github.com/toozservis-tech/TOOZHUB2/settings
```

## Troubleshooting

### If you don't see "Security" in Settings:

1. Make sure you have **admin/owner** permissions on the repository
2. If it's an organization repository, you may need organization admin permissions
3. Try accessing via direct link: `https://github.com/toozservis-tech/TOOZHUB2/settings/security_analysis`

### If "Secret scanning" is grayed out:

- This feature might not be available for your GitHub plan
- Check your GitHub plan: Free plan has limited access, GitHub Advanced Security requires GitHub Enterprise
- For public repositories, secret scanning is available on all plans
- For private repositories, you may need GitHub Advanced Security

## Verification

After enabling:

1. Go to **"Security"** tab in your repository (top menu)
2. Click on **"Secret scanning"** in the left sidebar
3. You should see a list of any detected secrets (if any)
4. You can also see alerts in the **"Security"** tab → **"Security overview"**

## Additional Security Recommendations

1. **Enable branch protection rules** (Settings → Branches)
2. **Require pull request reviews** before merging
3. **Enable status checks** for CI/CD
4. **Set up CODEOWNERS** file for automatic reviewers
5. **Use GitHub Actions** for automated security checks (already set up in `.github/workflows/security.yml`)

## Notes

- Secret scanning is **free for public repositories**
- For **private repositories**, you may need GitHub Advanced Security (paid feature)
- Scanning happens automatically on every push
- Historical commits are also scanned retroactively
- You'll receive email notifications if secrets are detected

