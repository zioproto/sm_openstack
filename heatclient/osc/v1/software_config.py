#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#

"""Orchestration v1 software config action implementations"""

import logging
import six

from six.moves.urllib import request
import yaml

from cliff import command
from cliff import lister
from openstackclient.common import exceptions as exc
from openstackclient.common import utils

from heatclient.common import format_utils
from heatclient.common import template_format
from heatclient.common import utils as heat_utils
from heatclient import exc as heat_exc
from heatclient.openstack.common._i18n import _


class DeleteConfig(command.Command):
    """Delete software configs"""

    log = logging.getLogger(__name__ + ".DeleteConfig")

    def get_parser(self, prog_name):
        parser = super(DeleteConfig, self).get_parser(prog_name)
        parser.add_argument(
            'id',
            metavar='<ID>',
            nargs='+',
            help=_('IDs of the software configs to delete')
        )
        return parser

    def take_action(self, parsed_args):
        self.log.debug("take_action(%s)", parsed_args)

        heat_client = self.app.client_manager.orchestration
        return _delete_config(heat_client, parsed_args)


def _delete_config(heat_client, args):
    failure_count = 0

    for config_id in args.id:
        try:
            heat_client.software_configs.delete(
                config_id=config_id)
        except Exception as e:
            if isinstance(e, heat_exc.HTTPNotFound):
                print(_('Software config with ID %s not found') % config_id)
            failure_count += 1
            continue

    if failure_count:
        raise exc.CommandError(_('Unable to delete %(count)s of the '
                                 '%(total)s software configs.') %
                               {'count': failure_count,
                                'total': len(args.id)})


class ListConfig(lister.Lister):
    """List software configs"""

    log = logging.getLogger(__name__ + ".ListConfig")

    def get_parser(self, prog_name):
        parser = super(ListConfig, self).get_parser(prog_name)
        parser.add_argument(
            '--limit',
            metavar='<LIMIT>',
            help=_('Limit the number of configs returned')
        )
        parser.add_argument(
            '--marker',
            metavar='<ID>',
            help=_('Return configs that appear after the given config ID')
        )
        return parser

    def take_action(self, parsed_args):
        self.log.debug("take_action(%s)", parsed_args)
        heat_client = self.app.client_manager.orchestration
        return _list_config(heat_client, parsed_args)


def _list_config(heat_client, args):
    kwargs = {}
    if args.limit:
        kwargs['limit'] = args.limit
    if args.marker:
        kwargs['marker'] = args.marker
    scs = heat_client.software_configs.list(**kwargs)

    columns = ['id', 'name', 'group', 'creation_time']
    return (columns, (utils.get_item_properties(s, columns) for s in scs))


class CreateConfig(format_utils.JsonFormat):
    """Create software config"""

    log = logging.getLogger(__name__ + ".CreateConfig")

    def get_parser(self, prog_name):
        parser = super(CreateConfig, self).get_parser(prog_name)
        parser.add_argument(
            'name',
            metavar='<CONFIG_NAME>',
            help=_('Name of the software config to create')
        )
        parser.add_argument(
            '--config-file',
            metavar='<FILE or URL>',
            help=_('Path to JSON/YAML containing map defining '
                   '<inputs>, <outputs>, and <options>')
        )
        parser.add_argument(
            '--definition-file',
            metavar='<FILE or URL>',
            help=_('Path to software config script/data')
        )
        parser.add_argument(
            '--group',
            metavar='<GROUP_NAME>',
            default='Heat::Ungrouped',
            help=_('Group name of tool expected by the software config')
        )
        return parser

    def take_action(self, parsed_args):
        self.log.debug("take_action(%s)", parsed_args)
        heat_client = self.app.client_manager.orchestration
        return _create_config(heat_client, parsed_args)


def _create_config(heat_client, args):
    config = {
        'group': args.group,
        'config': ''
    }

    defn = {}
    if args.definition_file:
        defn_url = heat_utils.normalise_file_path_to_url(
            args.definition_file)
        defn_raw = request.urlopen(defn_url).read() or '{}'
        defn = yaml.load(defn_raw, Loader=template_format.yaml_loader)

    config['inputs'] = defn.get('inputs', [])
    config['outputs'] = defn.get('outputs', [])
    config['options'] = defn.get('options', {})

    if args.config_file:
        config_url = heat_utils.normalise_file_path_to_url(
            args.config_file)
        config['config'] = request.urlopen(config_url).read()

    # build a mini-template with a config resource and validate it
    validate_template = {
        'heat_template_version': '2013-05-23',
        'resources': {
            args.name: {
                'type': 'OS::Heat::SoftwareConfig',
                'properties': config
            }
        }
    }
    heat_client.stacks.validate(template=validate_template)

    config['name'] = args.name
    sc = heat_client.software_configs.create(**config).to_dict()
    rows = list(six.itervalues(sc))
    columns = list(six.iterkeys(sc))
    return columns, rows
