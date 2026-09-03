# Tailcat Snap

Unofficial, community-maintained snap packaging for [tailcat](https://github.com/tailscale/tailcat)
-- like netcat, but over Tailscale's data plane (WireGuard, DERP-relayed NAT traversal), without
Tailscale's control plane. No account, no root/admin access; everything runs in userspace via a
gVisor netstack.

## Quick start

```sh
sudo snap install tailcat
tailcat --help
```

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for how to build this
package from source and run its test suite locally.

## Available feature and known limitations

This is a strictly confined snap, so some features may not be available due to AppArmor
restrictions. Please see [available features](./docs/available_features.md) and [known
limitations](./docs/known_limitations.md) for more information.

## License

`BSD-3-Clause` - matching [upstream tailcat](https://github.com/tailscale/tailcat).
