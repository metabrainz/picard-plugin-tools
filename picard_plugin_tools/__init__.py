import ast
import json
import os
import re
import zipfile

from hashlib import md5

import click

# The file that contains json data
PLUGIN_FILE_NAME = "PLUGINS.json"

URL_REGEX = r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)"
VERSION_REGEX = r"(\d+\.(\d+\.)*\d+)"


# ===================================
# Classes to validate manifest inputs
# ===================================


class VersionString(click.ParamType):
    name = "version_string"

    def convert(self, value, param, ctx):
        if not re.match(VERSION_REGEX, value):
            self.fail('%s is not a valid version string' % value, param, ctx)
        else:
            return value


class APIVersions(click.ParamType):
    name = "api_versions"

    def convert(self, value, param, ctx):
        api_versions = [v.strip() for v in value.split(",")]
        if not len(api_versions):
            self.fail('%s are not valid api versions' % value, param, ctx)
        for api_version in api_versions:
            if not re.match(VERSION_REGEX, api_version):
                self.fail('%s is not a valid API version' % api_version, param, ctx)
        return api_versions


class URLString(click.ParamType):
    name = "url_string"

    def convert(self, value, param, ctx):
        if not re.match(URL_REGEX, value):
            self.fail('%s is not a valid URL' % value, param, ctx)
        else:
            return value


KNOWN_DATA = {
    'PLUGIN_NAME': {'name': 'Plugin Name', 'type': str},
    'PLUGIN_AUTHOR': {'name': 'Plugin Author Name', 'type': str},
    'PLUGIN_VERSION': {'name': 'Plugin Version', 'type': VersionString()},
    'PLUGIN_API_VERSIONS': {'name': 'comma-separated Supported API Versions', 'type': APIVersions()},
    'PLUGIN_LICENSE': {'name': 'Plugin License', 'type': str},
    'PLUGIN_LICENSE_URL': {'name': 'License URL', 'type': URLString()},
    'PLUGIN_DESCRIPTION': {'name': 'Plugin Description', 'type': str},
}


def get_plugin_data(filepath):
    """Parse a python file and return a dict with plugin metadata"""
    data = {}
    with open(filepath, 'r') as plugin_file:
        source = plugin_file.read()
        try:
            root = ast.parse(source, filepath)
        except Exception:
            print("Cannot parse " + filepath)
            raise
        for node in ast.iter_child_nodes(root):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if (isinstance(target, ast.Name)
                    and isinstance(target.ctx, ast.Store)
                        and target.id in KNOWN_DATA):
                    name = target.id.replace('PLUGIN_', '', 1).lower()
                    if name not in data:
                        try:
                            data[name] = ast.literal_eval(node.value)
                        except ValueError:
                            print('Cannot evaluate value in '
                                  + filepath + ':' +
                                  ast.dump(node))
        return data


def create_manifest(filepath, manifest_data):
    with open(os.path.join(os.path.dirname(filepath), 'MANIFEST.json')) as f:
        f.write(json.dumps(manifest_data, sort_keys=True, indent=2))


def build_json(source_dir, dest_dir, supported_versions=None):
    """Traverse the plugins directory to generate json data."""

    plugins = {}

    # All top level directories in source_dir are plugins
    for dirname in next(os.walk(source_dir))[1]:

        files = {}
        data = {}

        if dirname in [".git"]:
            continue

        dirpath = os.path.join(source_dir, dirname)
        for root, dirs, filenames in os.walk(dirpath):
            for filename in filenames:
                ext = os.path.splitext(filename)[1]

                if ext not in [".pyc"]:
                    file_path = os.path.join(root, filename)
                    with open(file_path, "rb") as md5file:
                        md5Hash = md5(md5file.read()).hexdigest()
                    files[file_path.split(os.path.join(dirpath, ''))[1]] = md5Hash

                    if ext in ['.py'] and not data:
                        try:
                            data = get_plugin_data(os.path.join(source_dir, dirname, filename))
                        except SyntaxError:
                            print("Unable to parse %s" % filename)
        if files and data:
            print("Added: " + dirname)
            create_manifest(dirname, data)
            data['files'] = files
            plugins[dirname] = data
    out_path = os.path.join(dest_dir, PLUGIN_FILE_NAME)
    with open(out_path, "w") as out_file:
        json.dump({"plugins": plugins}, out_file, sort_keys=True, indent=2)


def get_valid_plugins(dest_dir):
    plugin_file = os.path.join(dest_dir, PLUGIN_FILE_NAME)
    if os.path.exists(plugin_file):
        with open(os.path.join(dest_dir, PLUGIN_FILE_NAME)) as f:
            plugin_data = json.loads(f.read())
            return list(plugin_data['plugins'].keys())


def package_files(source_dir, dest_dir):
    """Zip up plugin folders"""
    valid_plugins = get_valid_plugins(dest_dir)

    for dirname in next(os.walk(source_dir))[1]:
        if ((valid_plugins and dirname in valid_plugins)
            or not valid_plugins):
            archive_path = os.path.join(dest_dir, dirname) + ".picard.zip"
            archive = zipfile.ZipFile(archive_path, "w")

            dirpath = os.path.join(source_dir, dirname)
            plugin_files = []

            for root, dirs, filenames in os.walk(dirpath):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    plugin_files.append(file_path)

            if len(plugin_files) == 1:
                # There's only one file, put it directly into the zipfile
                archive.write(plugin_files[0],
                              os.path.basename(plugin_files[0]),
                              compress_type=zipfile.ZIP_DEFLATED)
            else:
                for filename in plugin_files:
                    # Preserve the folder structure relative to source_dir
                    # in the zip file
                    name_in_zip = os.path.join(os.path.relpath(filename,
                                                               source_dir))
                    archive.write(filename,
                                  name_in_zip,
                                  compress_type=zipfile.ZIP_DEFLATED)
            with open(archive_path, "rb") as source, open(archive_path + ".md5", "w") as md5file:
                md5file.write(md5(source.read()).hexdigest())
            print("Created: " + archive_path)


def validate_plugin(archive_path):
    with open(archive_path, "rb") as source, open(archive_path + ".md5") as md5file:
        if md5file.read() == md5(source.read()).hexdigest():
            return True
    return False


@click.group()
def cli():
    pass


@cli.command()
@click.argument('plugin_dir', type=click.Path(exists=True))
@click.argument('manifest_path', type=click.Path(exists=True), required=False)
@click.argument('dest', type=click.Path(exists=True), required=False)
def package_folder(plugin_dir, manifest_path=None, dest=None):

    plugin_files = []
    parent_dir = os.path.dirname(plugin_dir)

    for root, dirs, filenames in os.walk(plugin_dir):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            plugin_files.append(file_path)

    if not dest:
        archive_path = os.path.basename(os.path.normpath(plugin_dir)) + ".picard.zip"
    else:
        archive_path = dest

    archive = zipfile.ZipFile(archive_path, "w")

    if len(plugin_files) == 1:
        # There's only one file, put it directly into the zipfile
        archive.write(plugin_files[0],
                      os.path.basename(plugin_files[0]),
                      compress_type=zipfile.ZIP_DEFLATED)
    else:
        for filename in plugin_files:
            # Preserve the folder structure relative to source_dir
            # in the zip file
            name_in_zip = os.path.join(os.path.relpath(filename,
                                                       parent_dir))
            archive.write(filename,
                          name_in_zip,
                          compress_type=zipfile.ZIP_DEFLATED)
    info_list = [{'filename': file.filename, 'crc': file.CRC} for file in archive.infolist()]
    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest_data = json.load(f)
            manifest_data['files'] = info_list
        with open(manifest_path, 'w') as f:
            json.dump(manifest_data, f)
        archive.write(manifest_path,
                      'MANIFEST.json',
                      compress_type=zipfile.ZIP_DEFLATED)
    info_list = archive.infolist()


@cli.command()
@click.argument('archive_path', type=click.Path(exists=True))
def verify_package(archive_path):
    archive = zipfile.ZipFile(archive_path)
    info_list = [{'filename': file.filename, 'crc': file.CRC} for file in archive.infolist() if file.filename != "MANIFEST.json"]
    with archive.open('MANIFEST.json') as f:
        verification_data = json.loads(str(f.read().decode()))['files']
        if info_list == verification_data:
            return True
        else:
            return False
    return False


def load_manifest(archive_path):
    archive = zipfile.ZipFile(archive_path)
    with archive.open('MANIFEST.json') as f:
        manifest_data = json.loads(str(f.read().decode()))
        return manifest_data


def _create_manifest(manifest_path, manifest_data=None, missing_fields=None):
    if not manifest_data:
        manifest_data = {}
    if not missing_fields:
        missing_fields = KNOWN_DATA
    for key, value in KNOWN_DATA.items():
        if key in missing_fields:
            manifest_data[key] = click.prompt("Please input %s" % value['name'], type=value['type'])
    with open(manifest_path, 'w') as f:
        json.dump(manifest_data, f, indent=2)
    return manifest_data


@cli.command()
@click.argument('manifest_path', type=click.Path())
def create_basic_manifest(manifest_path):
    _create_manifest(manifest_path)


@cli.command()
@click.argument('manifest_path', type=click.Path(exists=True))
def verify_manifest(manifest_path):
    try:
        manifest_data = json.load(open(manifest_path))
    except (FileNotFoundError, OSError):
        click.echo("Unable to find or read manifest file.")
    except json.decoder.JSONDecodeError:
        click.echo("Manifest is damaged. Invalid JSON file.")
    else:
        missing_fields = set(KNOWN_DATA.keys()) - set(manifest_data.keys())
        if missing_fields:
            click.echo("Manifest incomplete. Following data not found: %s" % ", ".join(missing_fields))
            if click.confirm("Would you like to fill this data now?"):
                manifest_data = _create_manifest(manifest_path, manifest_data, missing_fields)
        click.echo("Manifest Verified!")
        click.echo("="*20)
        click.echo("MANIFEST: {}".format(manifest_path))
        click.echo("-"*20)
        for key, value in manifest_data.items():
            click.echo("{}: {}".format(key, value))
        click.echo("="*20)
