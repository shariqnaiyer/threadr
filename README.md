# threadr

Find, resume, fork and map your coding-agent conversations. Works with [herdr](https://herdr.dev) and tmux.

## Install

```bash
claude plugin marketplace add shariqnaiyer/threadr
claude plugin install threadr@threadr
```

```bash
git clone https://github.com/shariqnaiyer/threadr ~/.threadr && ~/.threadr/install.sh
```

## Use

- `threadr <terms>`: find a past session, cd to its directory, resume it
- `/branch-out [label]`: fork this conversation into a new herdr workspace or tmux window
- `threadr tree`: see which sessions were forked from which ([how](docs/lineage.md))
- `threadr doctor`: check your setup

Claude Code today. [Adding an agent](docs/providers.md) is one file.

## License

MIT
