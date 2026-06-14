# Setting up a development environment

The HoloViews library is a project that provides a wide range of data interfaces and an extensible set of plotting backends, which means the development and testing process involves a broad set of libraries.

This guide describes how to install and configure development environments.

If you have any problems with the steps here, please reach out in the `dev` channel on [Discord](https://discord.gg/rb6gPXbdAr) or on [Discourse](https://discourse.holoviz.org/).

## Preliminaries

### Basic understanding of how to contribute to Open Source

If this is your first open-source contribution, please study one
or more of the below resources.

- [How to Get Started with Contributing to Open Source | Video](https://youtu.be/RGd5cOXpCQw)
- [Contributing to Open-Source Projects as a New Python Developer | Video](https://youtu.be/jTTf4oLkvaM)
- [How to Contribute to an Open Source Python Project | Blog post](https://www.educative.io/blog/contribue-open-source-python-project)

### Git

The HoloViews source code is stored in a [Git](https://git-scm.com) source control repository. The first step to working on HoloViews is to install Git onto your system. There are different ways to do this, depending on whether you use Windows, Mac, or Linux.

To install Git on any platform, refer to the [Installing Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) section of the [Pro Git Book](https://git-scm.com/book/en/v2).

To contribute to HoloViews, you will also need [Github account](https://github.com/join) and knowledge of the [_fork and pull request workflow_](https://docs.github.com/en/get-started/quickstart/contributing-to-projects).

### Pixi

Developing all aspects of HoloViews requires a wide range of packages in different environments, but for new contributors the `default` environment will be more than enough.

To make this more manageable, Pixi manages the developer experience. To install Pixi, follow [this guide](https://pixi.sh/latest/#installation).

#### Glossary

- Tasks: A task is what can be run with `pixi run <task-name>`. Tasks can be anything from installing packages to running tests.
- Environments: An environment is a set of packages installed in a virtual environment. Each environment has a name; you can run tasks in a specific environment with the `-e` flag. For example, `pixi run -e test-core test-unit` will run the `test-unit` task in the `test-core` environment.
- Lock-file: A lock-file is a file that contains all the information about the environments.

For more information, see the [Pixi documentation](https://pixi.sh/latest/).

:::{admonition} Note
:class: info

The first time you run `pixi`, it will create a `.pixi` directory in the source directory.
This directory will contain all the files needed for the virtual environments.
The `.pixi` directory can be large, so it is advised not to put the source directory into a cloud-synced directory.

:::

## Installing the Project

### Cloning the Project

The source code for the HoloViews project is hosted on [GitHub](https://github.com/holoviz/holoviews). The first thing you need to do is clone the repository.

1. Go to [github.com/holoviz/holoviews](https://github.com/holoviz/holoviews)
2. [Fork the repository](https://docs.github.com/en/get-started/quickstart/contributing-to-projects#forking-a-repository)
3. Run in your terminal: `git clone https://github.com/<Your Username Here>/holoviews`

The instructions for cloning above created a `holoviews` directory at your file system location.
This `holoviews` directory is the _source checkout_ for the remainder of this document, and your current working directory is this directory.

## Start developing

To start developing, run the following command, this will create an environment called `default` and install HoloViews in [editable mode](https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs):

```bash
pixi run install
```

:::{admonition} Note
:class: info

The first time you run it, it will create a `pixi.lock` file with information for all available environments.
This command will take a minute or so to run.

:::
:::{admonition} Advanced usage
:class: tip

Currently, an editable install needs to be run in each environment. So, if you want to install in the `test-core` environment, you can add `--environment` / `-e` to the command:

```bash
pixi run -e test-core install
```

:::

When this is finished, it is possible to run the following command to download the data HoloViews tests and examples depend upon.

```bash
pixi run download-data
```

All available tasks can be found by running `pixi task list`, the following sections will give a brief introduction to the most common tasks.

For setting up a complete development you can run:

```bash
pixi run setup-dev
```

This will run the `install` and `download-data` tasks, among other tasks deemed necessary for a development environment.

:::{admonition} Note
:class: info

You may want to update Pixi occasionally, especially when troubleshooting, to get the latest fixes and improvements:

```bash
pixi self-update
```

:::

### Syncing Git tags with upstream repository

If you are working from a forked repository of HoloViews, you will need to sync the tags with the upstream repo.
This is needed because the HoloViews version number depends on [`git tags`](https://git-scm.com/book/en/v2/Git-Basics-Tagging).
Syncing the git tags can be done with:

```bash
pixi run sync-git-tags
```

## Developer Environment

The `default` environment is meant to provide all the tools needed to develop HoloViews.

This environment can be created by running `pixi run install`, which will set up the environment and make an editable install of HoloViews.

To activate this environment you can run `pixi shell`, this is equivalent to `source venv/bin/activate` in a virtual environment or `conda activate` in a conda environment.

If you need to run a command directly instead of via `pixi`, you activate the environment and run your command (e.g. `pytest holoviews/tests/<somefile.py>`).

### VS Code

This environment can also be selected in your IDE. In VS Code, this can be done by running the command `Python: Select Interpreter` and choosing `{'default': Pixi}`.

<p style="text-align: center">
  <img
    src="https://assets.holoviews.org/static/dev_guide/001.png"
    alt="001"
    style="width: 45%; display: inline-block"
  />
  <img
    src="https://assets.holoviews.org/static/dev_guide/002.png"
    alt="002"
    style="width: 45%; display: inline-block"
  />
</p>

To confirm you are using this dev environment, check the bottom right corner:

![003](https://assets.holoviews.org/static/dev_guide/003.png)

### Jupyter Lab

You can launch Jupyter lab with the `default` environment with `pixi run lab`.
This can be advantageous when you need to edit the documentation or debug an example notebook.

## Linting

HoloViews uses [pre-commit](https://pre-commit.com/) to apply linting to HoloViews code. Linting can be run for all the files with:

```bash
pixi run lint
```

Linting can also be set up to run automatically with each commit; this is the recommended way because if linting is not passing, the [Continuous Integration](https://en.wikipedia.org/wiki/Continuous_integration) (CI) will also fail.

```bash
pixi run lint-install
```

:::{admonition} Note
:class: info

Alternatively, if you have `pre-commit` installed elsewhere you can run

```bash
pre-commit install  # To install
pre-commit run --all-files  # To run on all files
```

:::

## Testing

To help keep HoloViews maintainable, all Pull Requests (PR) with code changes should typically be accompanied by relevant tests. While exceptions may be made for specific circumstances, the default assumption should be that a Pull Request without tests will not be merged.

HoloViews provides a layered set of test commands, from quick local checks to full release regression. Choose the appropriate level based on your changes.

### Quick reference table

| Scenario | Command | What it covers | Est. time |
|----------|---------|----------------|-----------|
| **本地快速检查** | `pixi run check` | lint + type + 核心单元测试 | ~5-10 min |
| **核心单元验证** | `pixi run test-unit-core` | core/ + element/ + util/ + testing/ | ~3-8 min |
| **Bokeh 后端渲染** | `pixi run test-plotting-bokeh` | plotting/bokeh/ | ~5-15 min |
| **Matplotlib 后端渲染** | `pixi run test-plotting-mpl` | plotting/matplotlib/ | ~5-15 min |
| **Plotly 后端渲染** | `pixi run test-plotting-plotly` | plotting/plotly/ | ~3-10 min |
| **所有后端渲染** | `pixi run test-plotting` | 三个后端 + plotting/ 根 | ~15-40 min |
| **Notebook/Display 验证** | `pixi run test-ipython` | ipython/ display hooks | ~1-3 min |
| **Datashader 相关验证** | `pixi run test-datashader` | operation/test_datashader.py + downsample + decollation | ~3-10 min |
| **所有 Operation 测试** | `pixi run test-operation` | operation/ | ~5-15 min |
| **完整单元测试** | `pixi run test-unit` | holoviews/tests/ 全部 | ~20-60 min |
| **文档示例构建** | `pixi run test-example` | examples/ notebook 执行 | ~30-90 min |
| **完整回归** | `pixi run test-all` | test-unit + test-example | ~1-3 hr |
| **UI 测试** | `pixi run test-ui` | holoviews/tests/ui/ (Playwright) | ~5-20 min |
| **发布前检查** | `pixi run test-release` | lint + type + test-all | ~1-3 hr |

### Three levels of testing workflow

#### 1. 本地快速检查（日常开发）

在提交代码前，运行快速检查确保没有基本问题：

```bash
pixi run check
```

这会依次执行：
- `lint` — 代码格式和静态检查（ruff, typos, prettier 等）
- `type-ty` — 类型注解检查
- `test-unit-core` — 核心单元测试（不涉及渲染后端）

如果你的改动只涉及核心逻辑，这通常足够了。

#### 2. 专项验证（按模块修改）

根据你修改的模块，运行针对性的测试：

**修改了核心数据结构（core/, element/, util/）：**
```bash
pixi run test-unit-core
```

**修改了 Bokeh 后端：**
```bash
pixi run test-plotting-bokeh
```

**修改了 Matplotlib 后端：**
```bash
pixi run test-plotting-mpl
```

**修改了 Plotly 后端：**
```bash
pixi run test-plotting-plotly
```

**修改了跨后端渲染逻辑：**
```bash
pixi run test-plotting
```

**修改了 datashader / 大数据处理：**
```bash
pixi run test-datashader
```

**修改了 IPython notebook 集成 / display hooks：**
```bash
pixi run test-ipython
```

**修改了 Operation 系统：**
```bash
pixi run test-operation
```

#### 3. 完整回归和发布前检查

**PR 提交前完整回归：**
```bash
pixi run test-all
```

**发布前最终检查：**
```bash
pixi run test-release
```

### Unit tests

Unit tests are usually small tests executed with [pytest](https://docs.pytest.org). They can be found in `holoviews/tests/`.
Unit tests can be run with the `test-unit` task:

```bash
pixi run test-unit
```

:::{admonition} Single source of truth: Command ↔ Marker ↔ Directory mapping
:class: tip

All three layers (pixi tasks, pytest markers, and directory structure) are **one-to-one aligned**.
If you update one, update all three.

<!-- AUTO-GENERATED BY workflow_sync.py — DO NOT EDIT [docs-mapping-table]
| Pixi task              | pytest marker       | Directories / files                                                 |
|------------------------|---------------------|---------------------------------------------------------------------|
| `test-unit-core      ` | `core               ` | core/, element/, util/, … (8 total)                                 |
| `test-plotting-bokeh ` | `plotting_bokeh     ` | plotting/bokeh/                                                     |
| `test-plotting-mpl   ` | `plotting_mpl       ` | plotting/matplotlib/                                                |
| `test-plotting-plotly` | `plotting_plotly    ` | plotting/plotly/                                                    |
| `test-plotting       ` | `plotting           ` | plotting/test_comms.py, plotting/test_plotutils.py, plotting/test_renderclass.py |
| `test-ipython        ` | `ipython            ` | ipython/                                                            |
| `test-datashader     ` | `datashader         ` | operation/test_datashader.py, operation/test_downsample.py, core/test_decollation.py |
| `test-operation      ` | `operation          ` | operation/                                                          |
| `test-ui             ` | `ui                 ` | ui/                                                                 |
| `test-gpu            ` | `gpu                ` | marked explicitly with `@pytest.mark.gpu`                           |
<!-- END AUTO-GENERATED [docs-mapping-table] -->

**Equivalent invocations** — pick whichever layer fits your workflow:

```bash
# Via pixi (recommended for local dev)
pixi run test-plotting-bokeh

# Via pytest marker (works inside any pixi shell)
pytest holoviews/tests -m plotting_bokeh

# Via pytest CLI flag (same set as marker)
pytest holoviews/tests --plotting-bokeh

# Via raw directory (legacy, not recommended — may drift)
pytest holoviews/tests/plotting/bokeh
```

Task environments: `test-310`, `test-311`, `test-312`, `test-313`, `test-314`, and `test-core`.
The first five differ only in Python version; `test-core` has only the minimal dependency set.

```bash
pixi run -e test-310 test-unit-core
```

:::

### Example tests

HoloViews's documentation consists mainly of Jupyter Notebooks. The example tests execute all the notebooks and fail if an error is raised. Example tests are possible thanks to [nbval](https://nbval.readthedocs.io/) and can be found in the `examples/` folder.
Example tests can be run with the following command:

```bash
pixi run test-example
```

This task has the same environments as the unit tests except for `test-core`.

### UI tests

HoloViews provides web components that users can interact with through the browser. UI tests allow checking that these components get displayed as expected and that the backend <-> front-end bi-communication works correctly. UI tests are possible thanks to [Playwright](https://playwright.dev/python/).
The test can be found in the `holoviews/tests/ui/` folder.
UI tests can be run with the following task. This task is only available in the `test-ui` environment. The first time you run it, it will download the necessary browser files to run the tests in the Chrome browser.

```bash
pixi run test-ui
```

### GPU tests

For GPU-accelerated code paths (cuDF, CuPy), use the `test-gpu` environment:

```bash
pixi run -e test-gpu test-gpu
```

Requires CUDA-compatible hardware and Linux.

### Workflow map — single source of truth

All test groups, their markers, pixi tasks, and CI jobs are defined in a single place:
[`scripts/workflow_map.py`](https://github.com/holoviz/holoviews/blob/main/scripts/workflow_map.py).
This file is the **single source of truth (SSOT)** for the entire developer workflow.

How it works:

1. **The map** defines each group with its path patterns, marker name, description,
   and whether it's excluded by default.
2. **Dynamic marking** — [conftest.py](file:///Users/pkcha/holoviews/holoviews/tests/conftest.py)
   loads the map at collection time and applies markers to each test based on its file path.
   No need to add `pytestmark` to individual files (though you can if you want grep-friendly markers).
3. **Consistency guard** — `python scripts/workflow_sync.py check` verifies that
   `conftest.py` fallback list, `pyproject.toml` markers, `pixi.toml` tasks, and
   documentation are all in sync with the map. This runs automatically in CI.
4. **Sync helper** — `python scripts/workflow_sync.py sync` auto-updates derived
   artifacts (conftest fallback, pyproject.toml markers, file-level pytestmarks)
   to match the map.

Common commands:

```bash
# See current state and all checks
python scripts/workflow_sync.py status

# Verify consistency (CI runs this)
python scripts/workflow_sync.py check

# Auto-update derived files after modifying the map
python scripts/workflow_sync.py sync
```

To add a new test group or reorganize existing ones:

1. Edit `scripts/workflow_map.py` — add/modify `WorkflowGroup` entries
2. Run `python scripts/workflow_sync.py sync` — updates conftest, pyproject.toml, file markers
3. Manually update `pixi.toml` tasks and docs if needed
4. Run `python scripts/workflow_sync.py check` — confirm everything is consistent
5. Commit both the map changes and the synchronized files

## Documentation

### Full documentation build

The complete documentation can be built with the command:

```bash
pixi run docs-build
```

As HoloViews uses notebooks for much of the documentation, this will take significant time to run (around an hour).

A development version of HoloViews can be found [here](https://dev.holoviews.org/). You can ask a maintainer if they want to make a dev release for your PR, but there is no guarantee they will say yes.

### Quick documentation build

For faster local iteration during documentation-only changes, use the quick build which disables both the user gallery and reference gallery:

```bash
pixi run docs-build-quick
```

This is equivalent to setting:
```bash
export HV_DOC_GALLERY=False
export HV_DOC_REF_GALLERY=False
pixi run docs-build
```

## Build

HoloViews have two build tasks. One is for building packages for Pip, and the other is for building packages for Conda.

```bash
pixi run build-pip
pixi run build-conda
```

## Making a pull requests

Once you have finished your code changes, you are ready to make a pull request.
A pull request is how code from your local repository becomes available to maintainers to review
and then merged into the project. To submit a pull request:

1.  Navigate to your repository on GitHub.
1.  Click on the `Compare & pull request` button.
1.  You can then look at the commits and file changes to make sure everything looks
    okay one last time.
1.  Write a descriptive title that includes prefixes. HoloViews uses a convention for title
    prefixes. The following prefixes are used:

        * build: Changes that affect the build system
        * chore: Changes that are not user-facing
        * ci: Changes to CI configuration files and scripts
        * compat: Compatibility with upstream packages
        * docs: Documentation only changes
        * enh: An enhancement to existing feature
        * feat: A new feature
        * fix: A bug fix
        * perf: A code change that improves performance
        * refactor: A code change that neither fixes a bug nor adds a feature
        * test: Adding missing tests or correcting existing tests
        * type: Type annotations

1.  Write a description of your changes in the `Write` tab, and check if everything looks ok in the `Preview` tab.
1.  Click `Create Pull Request`.

## Continuous Integration

Every push to the `main` branch or any PR branch on GitHub automatically triggers a test build with [GitHub Actions](https://github.com/features/actions).

You can see the list of all current and previous builds at [this URL](https://github.com/holoviz/holoviews/actions)

### Etiquette

GitHub Actions provides free build workers for open-source projects. A few considerations will help you be considerate of others needing these limited resources:

- Run the tests locally before opening or pushing to an opened PR.

- Group commits to meaningful chunks of work before pushing to GitHub (i.e., don't push on every commit).
