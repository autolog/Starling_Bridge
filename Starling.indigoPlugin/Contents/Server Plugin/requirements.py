#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Requirements Checking © Autolog 2023
#

from packaging import version
import pkg_resources

# ============================== Custom Imports ===============================
try:
    # noinspection PyUnresolvedReferences
    import indigo
except ImportError:
    pass

# import time  # TODO: REMOVE THIS AS DEBUGGING ONLY

def requirements_check(plugin_id):
    try:
        # time.sleep(10)

        # see https://stackoverflow.com/questions/10214827/find-which-version-of-package-is-installed-with-pip
        packages = [dist.project_name for dist in pkg_resources.working_set]
        packages_dict = dict()
        try:
            for count, item in enumerate(packages):
                packages_dict[item] = pkg_resources.get_distribution(item).version
        except:  # noqa
            pass
        plugin_info = indigo.server.getPlugin(plugin_id)
        requirements_path_fn = f"{plugin_info.pluginFolderPath}/Contents/Server Plugin/requirements.txt"

        # Process each package entry in the requirements.txt file
        file = open(requirements_path_fn, 'r')
        while True:
            line = file.readline()
            if line == '': break
            requirements_package, requirements_version = line.split("==")
            try:
                plugin_package_version = packages_dict[requirements_package]
            except KeyError as e:
                raise ImportError(f"'{requirements_package}' Package missing.\n\n========> Run 'pip3 install {requirements_package}' in Terminal window, then reload plugin. <========\n")

            if version.parse(plugin_package_version) < version.parse(requirements_version):
                raise ImportError(
                    f"'{requirements_package}' Package should be updated.\n\n========> Run 'pip3 install --upgrade {requirements_package}' in a Terminal window, then reload plugin. <========\n")
    except IOError as e:
        raise IOError(f"Unable to access requirements file to check required packages. IO Error: {e}")
