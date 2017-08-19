# picard-plugin-tools
Tools to manage Picard plugins.

## Usage:
    ppt [OPTIONS] COMMAND [ARGS]...

### Commands:
* **create_basic_manifest**     Creates a manifest file for a plugin with an interactive wizard.
* **package_folder**            Creates a plugin package from a given unpackaged plugin folder
* **verify_manifest**           Verifies if the manifest file for a plugin is valid and prompts for missing fields.
* **verify_package**            Verifies the checksum of a packaged plugin and verifies its integrity

### Help:
    ppt --help
    ppt COMMAND --help
