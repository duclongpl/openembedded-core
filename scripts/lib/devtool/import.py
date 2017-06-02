# Development tool - import command plugin
#
# Copyright (C) 2014-2017 Intel Corporation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""Devtool import plugin"""

import os
import tarfile
import logging
import re
from devtool import standard, setup_tinfoil
from devtool import export

import oeqa.utils.ftools as ftools
import json

logger = logging.getLogger('devtool')

def devimport(args, config, basepath, workspace):
    """Entry point for the devtool 'import' subcommand"""

    def get_pn(name):
        dirpath, recipe = os.path.split(name)
        pn = ""
        for sep in "_ .".split():
            if sep in recipe:
                pn = recipe.split(sep)[0]
                break
        return pn
    
    # match exported workspace folders
    prog = re.compile('recipes|appends|sources')

    if not os.path.exists(args.file):
        logger.error('Tar archive %s does not exist. Export your workspace using "devtool export"')
        return 1

    # get current recipes
    current_recipes = []
    try:
        tinfoil = setup_tinfoil(config_only=False, basepath=basepath)
        current_recipes = [recipe[1] for recipe in tinfoil.cooker.recipecaches[''].pkg_fn.items()]
    finally:
        tinfoil.shutdown()

    imported = []
    with tarfile.open(args.file) as tar:

        # get exported metadata so values containing paths can be automatically replaced it
        export_workspace_path = export_workspace = None
        try:
            metadata = tar.getmember(export.metadata)
            tar.extract(metadata)
            with open(metadata.name) as fdm:
                export_workspace_path, export_workspace = json.load(fdm)
            os.unlink(metadata.name)
        except KeyError as ke:
            logger.warn('The export metadata file created by "devtool export" was not found')
            logger.warn('Manual editing is needed to correct paths on imported recipes/appends')

        members = [member for member in tar.getmembers() if member.name != export.metadata]
        for member in members:
            # make sure imported bbappend has its corresponding recipe (bb)
            if member.name.startswith('appends'):
                bbappend = get_pn(member.name)
                if bbappend:
                    if bbappend not in current_recipes:
                        # check that the recipe is not in the tar archive being imported
                        if bbappend not in export_workspace:
                            logger.warn('No recipe to append %s, skipping' % bbappend)
                            continue
                else:
                    logger.warn('bbappend name %s could not be detected' % member.name)
                    continue

            # extract file from tar
            path = os.path.join(config.workspace_path, member.name)
            if os.path.exists(path):
                if args.overwrite:
                    try:
                        tar.extract(member, path=config.workspace_path)
                    except PermissionError as pe:
                        logger.warn(pe)
                else:
                    logger.warn('File already present. Use --overwrite/-o to overwrite it: %s' % member.name)
            else:
                tar.extract(member, path=config.workspace_path)

            if member.name.startswith('appends'):
                recipe = get_pn(member.name)

                # Update EXTERNARLSRC
                if export_workspace_path:
                    # appends created by 'devtool modify' just need to update the workspace
                    ftools.replace_from_file(path, export_workspace_path, config.workspace_path)

                    # appends created by 'devtool add' need replacement of exported source tree
                    exported_srctree = export_workspace[recipe]['srctree']
                    if exported_srctree:
                        ftools.replace_from_file(path, exported_srctree, os.path.join(config.workspace_path, 'sources', recipe))

                # update .devtool_md5 file
                standard._add_md5(config, recipe, path)
                if recipe not in imported:
                    imported.append(recipe)

    logger.info('Imported recipes into workspace %s: %s' % (config.workspace_path, ' '.join(imported)))
    return 0

def register_commands(subparsers, context):
    """Register devtool import subcommands"""
    parser = subparsers.add_parser('import',
                                   help='Import tar archive into workspace',
                                   description='Import previously created tar archive into the workspace',
                                   group='advanced')
    parser.add_argument('file', metavar='FILE', help='Name of the tar archive to import')
    parser.add_argument('--overwrite', '-o', action="store_true", help='Overwrite previous export tar archive')
    parser.set_defaults(func=devimport)
