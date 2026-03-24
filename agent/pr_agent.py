from github import Github
import os


def prs(owner, repo_name, filename, content, plan, issue_number):
    try:
        # Step 1 — Connect to GitHub
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise Exception("GITHUB_TOKEN not set")

        g = Github(token)
        repo = g.get_repo(f"{owner}/{repo_name}")

        # if no issue exists — create one automatically
        if not issue_number:
            issue = repo.create_issue(
                title=f"Auto: {plan['steps'][0] if plan else 'code change'}",
                body=f"Automatically created by the agent pipeline.\n\n{plan}"
            )
            issue_number = issue.number

        branch_name = f"fix/issue-{issue_number}"

        # Step 2 — Get default branch SHA (fallback main -> master)
        try:
            main_branch = repo.get_branch("main")
        except Exception:
            main_branch = repo.get_branch("master")
        main_sha = main_branch.commit.sha
        base_branch = main_branch.name

        # Step 3 — Create branch, or reset it if it already exists from a previous run
        try:
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=main_sha
            )
        except Exception as e:
            if "422" in str(e) or "already exists" in str(e).lower():
                # Reset the existing branch to current main so the commit applies cleanly
                ref = repo.get_git_ref(f"heads/{branch_name}")
                ref.edit(sha=main_sha, force=True)
            else:
                raise

        # Step 4 — Get existing file SHA from base branch (required by GitHub API)
        contents = repo.get_contents(filename, ref=base_branch)

        # Step 5 — Commit updated file to the new branch
        repo.update_file(
            path=filename,
            message=f"fix: resolve issue #{issue_number}",
            content=content,
            sha=contents.sha,
            branch=branch_name
        )

        # Step 6 — Create Pull Request (handle case where PR already exists)
        try:
            pr = repo.create_pull(
                title=f"Fix for issue #{issue_number}",
                body=f"Resolves #{issue_number}\n\n{plan}",
                head=branch_name,
                base=base_branch
            )
            pr_url = pr.html_url
        except Exception as e:
            if "422" in str(e) or "already exists" in str(e).lower():
                # PR already open for this branch — find it and return its URL
                open_prs = repo.get_pulls(state="open", head=f"{owner}:{branch_name}")
                pr = next(iter(open_prs), None)
                pr_url = pr.html_url if pr else f"https://github.com/{owner}/{repo_name}/pulls"
            else:
                raise

        # Step 7 — Comment on the issue
        issue = repo.get_issue(issue_number)
        issue.create_comment("Fix is ready for review ✅")

        # Step 8 — Return success
        return {
            "success": True,
            "pr_url": pr_url
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }