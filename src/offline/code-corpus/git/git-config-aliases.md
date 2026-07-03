---
language: shell
tags: [git, config, aliases, diff, tag, archive, cleanup]
title: Git Config, Aliases & Utilities
description: Git configuration, useful aliases, tagging, diffs, and repository maintenance.
source: pattern
```

```bash
# ── Configuration ──
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
git config --global init.defaultBranch main
git config --global core.editor "code --wait"
git config --global core.autocrlf input          # Linux/macOS
git config --global core.autocrlf true           # Windows
git config --global pull.rebase true             # rebase on pull by default
git config --global fetch.prune true             # auto-prune on fetch
git config --global diff.tool vscode
git config --global merge.tool vimdiff
git config --global color.ui auto
git config --list                                # show all config
git config --global --edit                       # open config in editor

# ── Useful Aliases ──
git config --global alias.lg "log --graph --oneline --all --decorate"
git config --global alias.aa "add -A"
git config --global alias.ci "commit"
git config --global alias.st "status -sb"
git config --global alias.br "branch -a"
git config --global alias.co "checkout"
git config --global alias.rb "rebase"
git config --global alias.unstage "restore --staged"
git config --global alias.last "log -1 HEAD"
git config --global alias.undo "reset --soft HEAD~1"
git config --global alias.df "diff --word-diff"
git config --global alias.cp "cherry-pick"
git config --global alias.who "shortlog -sn --no-merges"

# ── Diff Tools ──
git diff                                        # unstaged changes
git diff --staged                               # staged changes
git diff main..feature                          # branch comparison
git diff HEAD~5..HEAD                           # commit range
git diff --word-diff                            # word-level diff
git difftool                                    # use external diff tool

# ── Tagging ──
git tag v1.0.0                                  # lightweight tag
git tag -a v1.0.0 -m "Release v1.0.0"          # annotated tag
git tag -a v1.0.0 abc1234 -m "Tag later"       # tag specific commit
git tag -l "v1.*"                               # list tags by pattern
git push origin --tags                          # push all tags
git push origin v1.0.0                          # push specific tag
git tag -d v1.0.0                               # delete local tag
git push origin :refs/tags/v1.0.0              # delete remote tag

# ── Archive & Cleanup ──
git archive --format zip HEAD > project.zip     # zip current state
git archive --format tar HEAD | gzip > project.tar.gz
git gc                                          # garbage collection
git gc --aggressive --prune=now                # aggressive cleanup
git count-objects -vH                          # repo size
git repack -a -d --depth=500 --window=500      # repack for performance
git prune                                       # remove dangling objects
git clean -nd                                   # dry-run: show untracked files
git clean -fd                                   # remove untracked files/dirs

# ── .gitignore patterns ──
# .env
# node_modules/
# __pycache__/
# *.pyc
# .DS_Store
# dist/
# build/
# *.log
# .idea/
# *.swp
