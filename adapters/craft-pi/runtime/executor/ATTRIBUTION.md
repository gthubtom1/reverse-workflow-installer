# Attribution

This owned deterministic executor uses Craft Anything at commit `0326b4de8051f85a0f3139cd82f88f76911e6a35`, by ArtCraft Team and the Craft Anything contributors, under MIT OR Apache-2.0. The unchanged license texts accompany this source. A distributed build must include the reviewed ordered local policy patches and their hashes. The original project repository is https://github.com/storytold/craft-anything.

The executor invokes the separately owned `craft-pi-bridge` Rust driver. It invokes official Pi as an external pinned Node CLI; the Pi package, private provider definitions, credentials, personal configuration, REA and Spec packages are not included here. No official Pi/REA/Spec source modifications are made.

The staging script compiles source in a fresh relative layout, inspects actual PE imports and copies only the required GNU runtime DLLs. Any such DLL must retain its upstream license/notice obligations. No Craft desktop branding assets are packaged by this entry.
