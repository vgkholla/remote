from pathlib import Path

import pytest

from remote.configuration import RemoteConfig, SyncIgnores, WorkspaceConfig
from remote.configuration.shared import hash_path
from remote.configuration.toml import (
    DEFAULT_REMOTE_ROOT,
    GLOBAL_CONFIG,
    WORKSPACE_CONFIG,
    ConnectionConfig,
    GeneralConfig,
    GlobalConfig,
    LocalConfig,
    SyncRulesConfig,
    TomlConfigurationMedium,
    WorkCycleConfig,
    load_global_config,
    load_local_config,
    save_global_config,
)
from remote.exceptions import ConfigurationError


def test_load_global_config(mock_home):
    config_file = mock_home / GLOBAL_CONFIG
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        """\
[general]
allow_uninitiated_workspaces = true
remote_root = "my-remotes"

[[hosts]]
host = "test-host.example.com"
default = true

[push]
exclude = ["env", ".git"]

[pull]
exclude = ["src/generated"]

[both]
exclude = ["build"]
"""
    )

    config = load_global_config()
    assert config == GlobalConfig(
        hosts=[ConnectionConfig(host="test-host.example.com", directory=None, default=True)],
        push=SyncRulesConfig(exclude=["env", ".git"]),
        pull=SyncRulesConfig(exclude=["src/generated"]),
        both=SyncRulesConfig(exclude=["build"]),
        general=GeneralConfig(allow_uninitiated_workspaces=True, remote_root="my-remotes"),
    )


def test_load_global_config_no_file(mock_home):
    config = load_global_config()
    assert config == GlobalConfig(
        hosts=None,
        push=None,
        pull=None,
        both=None,
        general=GeneralConfig(allow_uninitiated_workspaces=False, remote_root=DEFAULT_REMOTE_ROOT),
    )


@pytest.mark.parametrize(
    "config_text, error_text",
    [
        (
            """\
[[hosts]]
host = "other-host.example.com"
default = "meow"

[push]
exclude = ["env", ".git"]
""",
            """\
Invalid value in configuration file /root/.config/remote/defaults.toml:
  - hosts.0.default: value could not be parsed to a boolean\
""",
        ),
        (
            """\
[[hosts]]
host = "other-host.example.com"
directory = ".remotes/other-workspace"
default = true

[push]
exclude = ["env", ".git"]
""",
            """\
Invalid value in configuration file /root/.config/remote/defaults.toml:
  - hosts: cannot specify directory in global host config\
""",
        ),
        (
            """\
[[hosts]]
host = "other-host.example.com"
default = true
meow = "mewo"

[push]
exclude = ["env", ".git"]
""",
            """\
Invalid value in configuration file /root/.config/remote/defaults.toml:
  - hosts.0.meow: extra fields not permitted\
""",
        ),
    ],
)
def test_load_global_config_error(mock_home, config_text, error_text):
    config_file = mock_home / GLOBAL_CONFIG
    config_file.parent.mkdir(parents=True)
    config_file.write_text(config_text)

    with pytest.raises(ConfigurationError) as e:
        load_global_config()

    assert str(e.value).replace(str(mock_home), "/root") == error_text


def test_save_global_config(mock_home):
    save_global_config(
        GlobalConfig(
            hosts=[ConnectionConfig(host="test-host.example.com", directory=None, default=True)],
            push=SyncRulesConfig(exclude=["env", ".git"]),
            pull=SyncRulesConfig(exclude=["src/generated"]),
            both=SyncRulesConfig(exclude=["build"]),
            general=GeneralConfig(allow_uninitiated_workspaces=True, remote_root="my-remotes"),
        )
    )

    assert (
        (mock_home / GLOBAL_CONFIG).read_text()
        == """\
[[hosts]]
host = "test-host.example.com"
default = true

[push]
exclude = [ "env", ".git",]

[pull]
exclude = [ "src/generated",]

[both]
exclude = [ "build",]

[general]
allow_uninitiated_workspaces = true
use_relative_remote_paths = false
remote_root = "my-remotes"
"""
    )


def test_load_local_config(tmp_path):
    config_file = tmp_path / WORKSPACE_CONFIG
    config_file.write_text(
        """\
[[hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"

[[hosts]]
host = "other-host.example.com"
directory = ".remotes/other-workspace"
default = true

[push]
exclude = ["env", ".git"]

[pull]
exclude = ["src/generated"]

[both]
exclude = ["build"]
"""
    )

    config = load_local_config(tmp_path)
    assert config == LocalConfig(
        hosts=[
            ConnectionConfig(host="test-host.example.com", directory=".remotes/workspace", default=False),
            ConnectionConfig(host="other-host.example.com", directory=".remotes/other-workspace", default=True),
        ],
        push=SyncRulesConfig(exclude=["env", ".git"]),
        pull=SyncRulesConfig(exclude=["src/generated"]),
        both=SyncRulesConfig(exclude=["build"]),
        extends=None,
    )


def test_load_local_config_with_extensions(tmp_path):
    config_file = tmp_path / WORKSPACE_CONFIG
    config_file.write_text(
        """\
[[extends.hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"

[extends.push]
exclude = ["env", ".git"]

[both]
exclude = ["build"]
"""
    )

    config = load_local_config(tmp_path)
    assert config == LocalConfig(
        hosts=None,
        push=None,
        pull=None,
        both=SyncRulesConfig(exclude=["build"]),
        extends=WorkCycleConfig(
            hosts=[ConnectionConfig(host="test-host.example.com", directory=".remotes/workspace", default=False)],
            push=SyncRulesConfig(exclude=["env", ".git"]),
            pull=None,
            both=None,
        ),
    )


def test_load_local_config_no_file(tmp_path):
    config = load_local_config(tmp_path)
    assert config == LocalConfig(hosts=None, push=None, pull=None, both=None, extends=None)


@pytest.mark.parametrize(
    "config_text, error_text",
    [
        (
            """\
[[hosts]]
host = "other-host.example.com"
directory = ".remotes/other-workspace"

[[extends.hosts]]
host = "other-host.example.com"
directory = ".remotes/other-workspace"
""",
            "Following fields are specified in for overwrite and extend in /root/.remote.toml file: hosts.",
        ),
        (
            """\
[general]
allow_uninitiated_workspaces = true
remote_root = "my-remotes"

[[extends.hosts]]
host = "other-host.example.com"
directory = ".remotes/other-workspace"
""",
            """\
Invalid value in configuration file /root/.remote.toml:
  - general: extra fields not permitted\
""",
        ),
    ],
)
def test_load_local_config_error(mock_home, config_text, error_text):
    config_file = mock_home / WORKSPACE_CONFIG
    config_file.write_text(config_text)

    with pytest.raises(ConfigurationError) as e:
        load_local_config(mock_home)

    assert str(e.value).replace(str(mock_home), "/root") == error_text


@pytest.mark.parametrize(
    "global_text, local_text, expected",
    [
        # All info goes from global config
        (
            """\
[general]
use_relative_remote_paths = true
allow_uninitiated_workspaces = true
remote_root = "my-remotes"

[[hosts]]
host = "test-host.example.com"

[[hosts]]
host = "other-host.example.com"
default = true

[push]
exclude = ["env", ".git"]

[pull]
exclude = ["src/generated"]

[both]
exclude = ["build"]
""",
            None,
            WorkspaceConfig(
                root=Path("/root/foo/bar"),
                configurations=[
                    RemoteConfig(host="test-host.example.com", directory=Path("my-remotes/foo/bar")),
                    RemoteConfig(host="other-host.example.com", directory=Path("my-remotes/foo/bar")),
                ],
                default_configuration=1,
                ignores=SyncIgnores(pull=["src/generated"], push=[".git", "env"], both=["build", ".remote.toml"]),
            ),
        ),
        # Settings from local config overwrite global ones
        (
            """\
[general]
use_relative_remote_paths = true

[[hosts]]
host = "other-host.example.com"
default = true

[push]
exclude = ["env", ".git"]

[pull]
exclude = ["src/generated"]

[both]
exclude = ["build"]
""",
            """\
[[hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"

[both]
exclude = []
""",
            WorkspaceConfig(
                root=Path("/root/foo/bar"),
                configurations=[RemoteConfig(host="test-host.example.com", directory=Path(".remotes/workspace"))],
                default_configuration=0,
                ignores=SyncIgnores(pull=["src/generated"], push=[".git", "env"], both=[".remote.toml"]),
            ),
        ),
        # Settings from local config extend and overwrite global ones. Defaults collision is resolved
        (
            """\
[general]
use_relative_remote_paths = true

[[hosts]]
host = "other-host.example.com"
default = true

[push]
exclude = ["env", ".git"]

[pull]
exclude = ["src/generated"]

[both]
exclude = ["build"]
""",
            """\
[[extends.hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"
default = true

[extends.push]
exclude = ["extend", "push"]

[both]
exclude = []
""",
            WorkspaceConfig(
                root=Path("/root/foo/bar"),
                configurations=[
                    RemoteConfig(host="other-host.example.com", directory=Path(".remotes/foo/bar")),
                    RemoteConfig(host="test-host.example.com", directory=Path(".remotes/workspace")),
                ],
                default_configuration=1,
                ignores=SyncIgnores(
                    pull=["src/generated"], push=[".git", "env", "extend", "push"], both=[".remote.toml"]
                ),
            ),
        ),
        # No global config
        (
            None,
            """\
[[hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"
default = true

[push]
exclude = ["extend", "push"]
""",
            WorkspaceConfig(
                root=Path("/root/foo/bar"),
                configurations=[RemoteConfig(host="test-host.example.com", directory=Path(".remotes/workspace"))],
                default_configuration=0,
                ignores=SyncIgnores(pull=[], push=["extend", "push"], both=[".remote.toml"]),
            ),
        ),
        # No global config at all, but there are some extends in local
        (
            None,
            """\
[[extends.hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"
default = true

[extends.push]
exclude = ["extend", "push"]

[both]
exclude = []
""",
            WorkspaceConfig(
                root=Path("/root/foo/bar"),
                configurations=[RemoteConfig(host="test-host.example.com", directory=Path(".remotes/workspace"))],
                default_configuration=0,
                ignores=SyncIgnores(pull=[], push=["extend", "push"], both=[".remote.toml"]),
            ),
        ),
        # No global config and no default set (first is default implicitely)
        (
            None,
            """\
[[hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"

[push]
exclude = ["extend", "push"]
""",
            WorkspaceConfig(
                root=Path("/root/foo/bar"),
                configurations=[RemoteConfig(host="test-host.example.com", directory=Path(".remotes/workspace"))],
                default_configuration=0,
                ignores=SyncIgnores(pull=[], push=["extend", "push"], both=[".remote.toml"]),
            ),
        ),
        # No local config, global config has no directory and supports relative remote paths
        (
            """\
[general]
allow_uninitiated_workspaces = true
use_relative_remote_paths = true
remote_root = "remote"

[[hosts]]
host = "test-host.example.com"

[push]
exclude = ["extend", "push"]
""",
            None,
            WorkspaceConfig(
                root=Path("/root/foo/bar"),
                configurations=[RemoteConfig(host="test-host.example.com", directory=Path("remote/foo/bar"))],
                default_configuration=0,
                ignores=SyncIgnores(pull=[], push=["extend", "push"], both=[".remote.toml"]),
            ),
        ),
    ],
)
def test_medium_load_config(mock_home, global_text, local_text, expected):
    global_config_file = mock_home / GLOBAL_CONFIG
    global_config_file.parent.mkdir(parents=True)
    if global_text:
        global_config_file.write_text(global_text)

    workspace = mock_home / "foo" / "bar"
    local_config_file = workspace / WORKSPACE_CONFIG
    local_config_file.parent.mkdir(parents=True)
    if local_text:
        local_config_file.write_text(local_text)

    medium = TomlConfigurationMedium()
    config = medium.load_config(workspace)
    # The path is randomly generated so we need to replace it
    config.root = Path(str(config.root).replace(str(mock_home), "/root"))

    assert config == expected


def test_medium_load_config_no_directory(mock_home):
    global_config_file = mock_home / GLOBAL_CONFIG
    global_config_file.parent.mkdir(parents=True)
    global_config_file.write_text(
        """
    [general]
allow_uninitiated_workspaces = true
remote_root = "my-remotes"

[[hosts]]
host = "test-host.example.com"
"""
    )
    workspace = mock_home / "foo" / "bar"

    medium = TomlConfigurationMedium()
    config = medium.load_config(workspace)
    # The path is randomly generated so we need to replace it
    config.root = Path(str(config.root).replace(str(mock_home), "/root"))

    assert config == WorkspaceConfig(
        root=Path("/root/foo/bar"),
        configurations=[
            RemoteConfig(
                host="test-host.example.com",
                directory=Path(f"my-remotes/bar_{hash_path(workspace)}"),
                shell="sh",
                shell_options="",
            )
        ],
        default_configuration=0,
        ignores=SyncIgnores(pull=[], push=[], both=[".remote.toml"]),
    )


def test_medium_load_config_picks_up_vsc_ignore_files(mock_home):
    text = """
[[hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"
default = true

[push]
exclude = ["env", ".git"]

[pull]
include_vsc_ignore_patterns = true

[both]
exclude = ["build"]
include_vsc_ignore_patterns = true
"""
    workspace = mock_home / "foo" / "bar"
    local_config_file = workspace / WORKSPACE_CONFIG
    local_config_file.parent.mkdir(parents=True)
    local_config_file.write_text(text)

    ignore_file = workspace / ".gitignore"
    ignore_file.write_text(
        """
# comment
# Comment
*.pattern

# comment

pattern_two

"""
    )

    medium = TomlConfigurationMedium()

    config = medium.load_config(workspace)

    # The path is randomly generated so we need to replace it
    config.root = Path(str(config.root).replace(str(mock_home), "/root"))

    assert config == WorkspaceConfig(
        root=Path("/root/foo/bar"),
        configurations=[RemoteConfig(host="test-host.example.com", directory=Path(".remotes/workspace"))],
        default_configuration=0,
        ignores=SyncIgnores(
            pull=["*.pattern", "pattern_two"],
            push=[".git", "env"],
            both=["build", ".remote.toml", "*.pattern", "pattern_two"],
        ),
    )


def test_medium_load_config_extension_overwrites_include_vsc_ignore_patterns(mock_home):
    global_config_file = mock_home / GLOBAL_CONFIG
    global_config_file.parent.mkdir(parents=True)
    global_config_file.write_text(
        """
[[hosts]]
host = "test-host.example.com"
default = true

[pull]
exclude = ["env"]
include_vsc_ignore_patterns = true
"""
    )

    workspace = mock_home / "foo" / "bar"
    local_config_file = workspace / WORKSPACE_CONFIG
    local_config_file.parent.mkdir(parents=True)
    local_config_file.write_text(
        """
[extends.pull]
exclude = ["build"]
include_vsc_ignore_patterns = false
"""
    )

    ignore_file = workspace / ".gitignore"
    ignore_file.write_text("*.pattern\npattern_two\n")

    medium = TomlConfigurationMedium()

    config = medium.load_config(workspace)

    # The path is randomly generated so we need to replace it
    config.root = Path(str(config.root).replace(str(mock_home), "/root"))

    # config is loaded but no patterns are present
    assert config.ignores.pull == ["build", "env"]


def test_medium_load_config_fails_on_no_hosts(mock_home):

    workspace = mock_home / "foo" / "bar"
    local_config_file = workspace / WORKSPACE_CONFIG
    local_config_file.parent.mkdir(parents=True)
    local_config_file.write_text(
        """\
[both]
exclude = []"""
    )

    medium = TomlConfigurationMedium()

    with pytest.raises(ConfigurationError) as e:
        medium.load_config(workspace)

    assert str(e.value) == "You need to provide at least one remote host to connect"


def test_medium_generate_remote_directory(mock_home, workspace_config):
    medium = TomlConfigurationMedium()
    medium._global_config = GlobalConfig(
        general=GeneralConfig(allow_uninitiated_workspaces=False, remote_root="my-root-for-test"),
    )
    generated_dir = medium.generate_remote_directory(workspace_config)

    assert str(generated_dir).startswith("my-root-for-test/workspace_")


def test_medium_is_workspace_root(mock_home):
    medium = TomlConfigurationMedium()
    global_config = GlobalConfig(
        general=GeneralConfig(allow_uninitiated_workspaces=False, remote_root="my-root-for-test"),
    )
    medium._global_config = global_config

    test_workspace = mock_home / "foo" / "bar"
    test_workspace.mkdir(parents=True)

    # No config - isn't workspace
    assert not medium.is_workspace_root(test_workspace)

    # Can find config - is workspace
    (test_workspace / WORKSPACE_CONFIG).write_text("[push]")
    assert medium.is_workspace_root(test_workspace)

    # No config, but uninitiated workspaces allowed - is workspace
    (test_workspace / WORKSPACE_CONFIG).unlink()
    global_config.general.allow_uninitiated_workspaces = True
    assert medium.is_workspace_root(test_workspace)


@pytest.mark.parametrize(
    "global_text, local_text, config, expected",
    [
        (
            None,
            None,
            WorkspaceConfig(
                root=Path("/root/foo/bar"),
                configurations=[
                    RemoteConfig(host="test-host.example.com", directory=Path(".remotes/workspace")),
                    RemoteConfig(host="other-host.example.com", directory=Path(".remotes/other-workspace")),
                ],
                default_configuration=1,
                ignores=SyncIgnores(pull=["src/generated"], push=[".git", "env"], both=["build", ".remote.toml"]),
            ),
            """\
[[hosts]]
host = "test-host.example.com"
directory = ".remotes/workspace"

[[hosts]]
host = "other-host.example.com"
directory = ".remotes/other-workspace"
default = true

[push]
exclude = [ ".git", "env",]

[pull]
exclude = [ "src/generated",]

[both]
exclude = [ ".remote.toml", "build",]
""",
        ),
    ],
)
def test_medium_save_config(mock_home, global_text, local_text, config, expected):
    global_config_file = mock_home / GLOBAL_CONFIG
    global_config_file.parent.mkdir(parents=True)
    if global_text:
        global_config_file.write_text(global_text)

    workspace = mock_home / "foo" / "bar"
    local_config_file = workspace / WORKSPACE_CONFIG
    local_config_file.parent.mkdir(parents=True)
    if local_text:
        local_config_file.write_text(local_text)

    config.root = workspace
    medium = TomlConfigurationMedium()
    medium.save_config(config)

    # Save function never touches the global config
    if not global_text:
        assert not global_config_file.exists()
    else:
        assert global_config_file.read_text() == global_text

    assert local_config_file.exists()
    assert local_config_file.read_text() == expected
