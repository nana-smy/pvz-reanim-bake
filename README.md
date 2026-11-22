# pvz-reanim-bake

Offline CI bake of the original *Plants vs. Zombies* (2009) `reanim` part animations
into packed WebP sprite strips, consumed by the [pvz-rs](https://github.com/nana-smy/pvz-rs) web build.

Assets come from the public extracted-asset mirror `FregD156/PvZ_Assets` (`reanim/` folder),
which is sparse-cloned at run time; nothing from it is redistributed here except the baked strips
used by the game demo.

The bake runs on a GitHub-hosted x86 runner because the local sandbox is not powerful enough
for ~2k part sprites × hundreds of frames.

See `report.json` / `out_reports/` for the last run's per-clip numbers.
