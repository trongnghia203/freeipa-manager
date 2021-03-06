#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: BSD-3-Clause
# Copyright © 2017-2019, GoodData Corporation. All rights reserved.

import logging
import mock
import os
import pytest
import sys
import yaml
from testfixtures import log_capture, LogCapture

from _utils import _import, _mock_dump
sys.modules['ipalib'] = mock.Mock()
tool = _import('ipamanager', 'ipa_connector')
tool.api = mock.MagicMock()
entities = _import('ipamanager', 'entities')
modulename = 'ipamanager.ipa_connector'
up_class = 'ipamanager.ipa_connector.IpaUploader'
SETTINGS = os.path.join(
    os.path.dirname(__file__), 'freeipa-manager-config/settings.yaml')


class TestIpaConnectorBase(object):
    def setup_method(self, method):
        self._create_uploader()

    def teardown_method(self, _):
        try:
            tool.api.Command.__getitem__.side_effect = self._api_call
        except AttributeError:
            pass

    def _create_uploader(self, **args):
        with open(SETTINGS) as settings_file:
            self.settings = yaml.safe_load(settings_file)

        self.uploader = tool.IpaUploader(
            settings=self.settings,
            parsed=args.get('parsed', {}),
            threshold=args.get('threshold', 0),
            force=args.get('force', False),
            enable_deletion=args.get('enable_deletion', False))
        self.uploader.commands = dict()
        self.uploader.ipa_entity_count = 0

    def _api_call(self, command):
        return {
            'group_find': self._api_find('group'),
            'hbacrule_find': self._api_find('rule'),
            'hostgroup_find': self._api_find('group'),
            'sudorule_find': self._api_find('rule'),
            'user_find': self._api_user_find,
            'permission_find': self._api_find('permission'),
            'privilege_find': self._api_find('privilege'),
            'role_find': self._api_find('role'),
            'hbacsvc_find': self._api_find('hbacsvc'),
            'hbacsvcgroup_find': self._api_find('hbacsvcgroup'),
            'service_find': self._api_service_find,
            'user_add': self._api_user_add,
            'group_add': self._api_add('group'),
            'hostgroup_add': self._api_add('hostgroup'),
            'hbacrule_add': self._api_add('hbacrule'),
            'sudorule_add': self._api_add('sudorule'),
            'group_add_member': self._api_nosummary,
            'hbacrule_add_user': self._api_nosummary,
            'hbacrule_add_host': self._api_nosummary,
            'sudorule_add_user': self._api_nosummary,
            'sudorule_add_host': self._api_nosummary
        }[command]

    def _api_call_unreliable(self, command):
        try:
            return {
                'group_add_member': self._api_fail,
                'hbacrule_add_user': self._api_fail,
                'sudorule_add_user': self._api_fail
            }[command]
        except KeyError:
            return self._api_call(command)

    def _api_call_find_fail(self, command):
        if command.endswith('find'):
            return self._api_exc
        return self._api_call(command)

    def _api_call_execute_fail(self, command):
        if command == 'group_add_member':
            return self._api_exc
        return self._api_call(command)

    def _api_user_find(self, **kwargs):
        return {'result': [{'uid': ('user.one',)}]}

    def _api_service_find(self, **kwargs):
        return {'result': [{'krbcanonicalname': ('service-one',)}]}

    def _api_find(self, name):
        def _func(**kwargs):
            return {'result': [{'cn': ('%s-one' % name)}]}
        return _func

    def _api_user_add(self, **kwargs):
        return {'summary': u'Added user "%s"' % kwargs.get('uid')}

    def _api_add(self, name):
        def _func(**kwargs):
            return {'summary': u'Added %s "%s"' % (name, kwargs.get('cn'))}
        return _func

    def _api_nosummary(self, **kwargs):
        return {u'failed': {u'attr1': {'param1': (), 'param2': ()}}}

    def _api_fail(self, **kwargs):
        return {
            u'failed': {u'attr1': {'param1': ((u'test', u'no such attr2'),)}}}

    def _api_exc(self, **kwargs):
        raise Exception('Some error happened')


class TestIpaConnector(TestIpaConnectorBase):
    def test_load_ipa_entities(self):
        tool.api.Command.__getitem__.side_effect = self._api_call
        self.uploader.load_ipa_entities()
        assert self.uploader.ipa_entities == {
            'group': {'g': entities.FreeIPAUserGroup(
                'g', {'cn': ('g',)})},
            'hbacrule': {'r': entities.FreeIPAHBACRule(
                'r', {'cn': ('r',)})},
            'hbacsvc': {'h': entities.FreeIPAHBACService(
                'h', {'cn': ('h',)})},
            'hbacsvcgroup': {'h': entities.FreeIPAHBACServiceGroup(
                'h', {'cn': ('h',)})},
            'hostgroup': {'g': entities.FreeIPAHostGroup(
                'g', {'cn': ('g',)})},
            'sudorule': {'r': entities.FreeIPASudoRule(
                'r', {'cn': ('r',)})},
            'user': {'user.one': entities.FreeIPAUser(
                'user.one', {'uid': ('user.one',)})},
            'service': {'service-one': entities.FreeIPAService(
                'service-one', {'krbcanonicalname': ('service-name',)})},
            'role': {'r': entities.FreeIPARole(
                'r', {'cn': ('r',)})},
            'permission': {'p': entities.FreeIPAPermission(
                'p', {'cn': ('p',)})},
            'privilege': {'p': entities.FreeIPAPrivilege(
                'p', {'cn': ('p',)})}}

    @log_capture('IpaUploader', level=logging.DEBUG)
    def test_load_ipa_entities_ignore(self, captured_log):
        tool.api.Command.__getitem__.side_effect = self._api_call
        self.uploader.ignored['user'] = ['user.one']
        self.uploader.load_ipa_entities()
        for cmd in ('group', 'hbacrule', 'hostgroup', 'sudorule',
                    'user', 'service', 'role', 'permission', 'privilege'):
            tool.api.Command.__getitem__.assert_any_call(
                '%s_find' % cmd)
        msgs = [(r.levelname, r.msg % r.args) for r in captured_log.records]
        assert ('DEBUG', 'Not parsing ignored user user.one') in msgs
        assert ('INFO', 'Parsed 10 entities from FreeIPA API') in msgs

    def test_load_ipa_entities_errors(self):
        tool.api.Command.__getitem__.side_effect = (
            self._api_call_find_fail)
        with pytest.raises(tool.ManagerError) as exc:
            self.uploader.load_ipa_entities()
        assert exc.value[0] == (
            'Error loading hbacrule entities from API: Some error happened')

    def test_load_ipa_entities_unknown_command(self):
        with mock.patch(
                'ipamanager.entities.FreeIPAUser.entity_name', 'users'):
            with pytest.raises(tool.ManagerError) as exc:
                self.uploader.load_ipa_entities()
            assert exc.value[0] == 'Undefined API command users_find'


class TestIpaUploader(TestIpaConnectorBase):
    def test_parse_entity_diff_add(self):
        entity = entities.FreeIPAUser(
            'test.user', {'firstName': 'Test', 'lastName': 'User'}, 'path')
        self.uploader.ipa_entities = {
            'user': dict(),
            'group': dict(),
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader.commands = []
        self.uploader._parse_entity_diff(entity)
        assert len(self.uploader.commands) == 1
        cmd = self.uploader.commands[0]
        assert cmd.command == 'user_add'
        assert cmd.description == (
            'user_add test.user (givenname=Test; sn=User)')
        assert cmd.payload == {
            'givenname': u'Test', 'sn': u'User', 'uid': u'test.user'}

    def test_parse_entity_diff_extended_latin(self):
        name = yaml.safe_load(u'Tešt')
        entity = entities.FreeIPAUser(
            'test.user', {'firstName': name, 'lastName': 'User'}, 'path')
        self.uploader.ipa_entities = {
            'user': dict(),
            'group': dict(),
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader.commands = []
        self.uploader._parse_entity_diff(entity)
        assert len(self.uploader.commands) == 1
        cmd = self.uploader.commands[0]
        assert cmd.command == 'user_add'
        assert cmd.description == (
            u'user_add test.user (givenname=Te\u0161t; sn=User)')
        assert cmd.payload == {
            'givenname': u'Te\u0161t', 'sn': u'User', 'uid': u'test.user'}

    def test_parse_entity_diff_mod(self):
        entity = entities.FreeIPAUser(
            'test.user',
            {'firstName': 'Test', 'lastName': 'User',
             'githubLogin': ['gh1', 'gh2']}, 'path')
        self.uploader.ipa_entities = {
            'user': {
                'test.user': entities.FreeIPAUser('test.user', {
                    'mail': (u'test.user@example.com',),
                    'carlicense': (u'gh1',)})},
            'group': dict(),
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader.commands = []
        self.uploader._parse_entity_diff(entity)
        assert len(self.uploader.commands) == 1
        cmd = self.uploader.commands[0]
        assert cmd.command == 'user_mod'
        assert cmd.description == (
            "user_mod test.user (carlicense=(u'gh1', u'gh2'); "
            "givenname=Test; mail=(); sn=User)")
        assert cmd.payload == {
            'carlicense': (u'gh1', u'gh2'), 'givenname': u'Test',
            'mail': (), 'sn': u'User', 'uid': u'test.user'}

    def test_parse_entity_diff_mod_extended_latin_same(self):
        name = yaml.safe_load(u'Tešt')
        entity = entities.FreeIPAUser(
            'test.user',
            {'firstName': name, 'lastName': 'User',
             'githubLogin': ['gh1']}, 'path')
        self.uploader.ipa_entities = {
            'user': {
                'test.user': entities.FreeIPAUser('test.user', {
                    'givenname': (u'Te\u0161t',),
                    'sn': (u'User',),
                    'carlicense': (u'gh1',)})},
            'group': dict(),
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader.commands = []
        self.uploader._parse_entity_diff(entity)
        assert len(self.uploader.commands) == 0

    def test_parse_entity_diff_mod_extended_latin(self):
        name = yaml.safe_load(u'Tešt')
        entity = entities.FreeIPAUser(
            'test.user',
            {'firstName': name, 'lastName': 'User',
             'githubLogin': ['gh1']}, 'path')
        self.uploader.ipa_entities = {
            'user': {
                'test.user': entities.FreeIPAUser('test.user', {
                    'givenname': (u'Test',),
                    'sn': (u'User',),
                    'carlicense': (u'gh1',)})},
            'group': dict(),
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader.commands = []
        self.uploader._parse_entity_diff(entity)
        assert len(self.uploader.commands) == 1
        cmd = self.uploader.commands[0]
        assert cmd.command == 'user_mod'
        assert cmd.description == u'user_mod test.user (givenname=Te\u0161t)'
        assert cmd.payload == {'givenname': u'Te\u0161t', 'uid': u'test.user'}

    def test_parse_entity_diff_memberof_add(self):
        self.uploader.repo_entities = {
            'user': {
                'test.user': entities.FreeIPAUser(
                    'test.user',
                    {'firstName': 'Test', 'lastName': 'User',
                     'memberOf': {'group': ['group-one']}}, 'path')},
            'group': {'group-one': entities.FreeIPAUserGroup(
                'group-one', {}, 'path')},
            'role': {},
            'privilege': {},
            'permission': {},
            'service': {}}
        self.uploader.ipa_entities = {
            'user': {'test.user': entities.FreeIPAUser('test.user', {
                'uid': ('test.user',),
                'givenname': (u'Test',), 'sn': (u'User',)})},
            'group': {'group-one': entities.FreeIPAUserGroup(
                'group-one', {'cn': ('group-one',)})},
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict()}
        self.uploader.commands = []
        self.uploader._parse_entity_diff(
            self.uploader.repo_entities['user']['test.user'])
        assert len(self.uploader.commands) == 1
        cmd = self.uploader.commands[0]
        assert cmd.command == 'group_add_member'
        assert cmd.description == (
            'group_add_member group-one (user=test.user)')
        assert cmd.payload == {'cn': u'group-one', 'user': u'test.user'}

    def test_parse_entity_diff_memberof_remove(self):
        self.uploader.repo_entities = {
            'user': {'test.user': entities.FreeIPAUser(
                'test.user', {'firstName': 'Test', 'lastName': 'User'},
                'path')},
            'group': {'group-one': entities.FreeIPAUserGroup(
                'group-one', {}, 'path')},
            'role': {},
            'privilege': {},
            'permission': {},
            'service': {}}
        self.uploader.ipa_entities = {
            'user': {'test.user': entities.FreeIPAUser('test.user', {
                'uid': ('test.user',),
                'givenname': (u'Test',), 'sn': (u'User',)})},
            'group': {
                'group-one': entities.FreeIPAUserGroup('group-one', {
                    'cn': ('group-one',), 'member_user': ('test.user',)})},
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader.commands = []
        self.uploader._parse_entity_diff(
            self.uploader.repo_entities['user']['test.user'])
        assert len(self.uploader.commands) == 1
        cmd = self.uploader.commands[0]
        assert cmd.command == 'group_remove_member'
        assert cmd.description == (
            'group_remove_member group-one (user=test.user)')
        assert cmd.payload == {'cn': u'group-one', 'user': u'test.user'}

    def test_prepare_push_same(self):
        self.uploader.repo_entities = {
            'user': {
                'test.user': entities.FreeIPAUser(
                    'test.user', {'firstName': 'Test', 'lastName': 'User',
                                  'memberOf': {'group': ['group-one']}},
                    'path')},
            'group': {'group-one': entities.FreeIPAUserGroup(
                'group-one', {}, 'path')},
            'role': {},
            'privilege': {},
            'permission': {},
            'service': {}}
        self.uploader.ipa_entities = {
            'user': {
                'test.user': entities.FreeIPAUser('test.user', {
                    'uid': ('test.user',),
                    'givenname': (u'Test',), 'sn': (u'User',)})},
            'group': {'group-one': entities.FreeIPAUserGroup('group-one', {
                'cn': ('group-one',), 'member_user': ('test.user',),
                'objectclass': (u'posixgroup',)})},
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader._prepare_push()
        assert len(self.uploader.commands) == 0

    @log_capture('IpaUploader', level=logging.INFO)
    def test_prepare_push_changes_addonly(self, captured_log):
        self._create_uploader(force=True)
        self.uploader.repo_entities = {
            'user': {
                'test.user': entities.FreeIPAUser(
                    'test.user',
                    {'firstName': 'Test', 'lastName': 'User',
                     'memberOf': {'group': ['group-one']}}, 'path')},
            'group': {'group-one': entities.FreeIPAUserGroup(
                'group-one', {}, 'path')},
            'sudorule': {
                'rule-one': entities.FreeIPASudoRule(
                    'rule-one', {'memberUser': ['group-one']}, 'path')}}
        self.uploader.ipa_entities = {
            'group': {'group-one': entities.FreeIPAUserGroup(
                'group-one', {'cn': ('group-one',), u'objectclass': (
                    u'posixgroup',)})}, 'user': dict(),
            'sudorule': {'rule-two': entities.FreeIPASudoRule(
                'rule-two', {'memberuser_group': (u'group_one',)})},
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader._prepare_push()
        assert len(self.uploader.commands) == 6
        assert [i.command for i in sorted(self.uploader.commands)] == [
            'sudorule_add', 'user_add', 'group_add_member',
            'sudorule_add_option', 'sudorule_add_option', 'sudorule_add_user']
        captured_log.check(('IpaUploader', 'INFO', '6 commands to execute'))

    def test_prepare_push_changes_deletion_enabled(self):
        self._create_uploader(enable_deletion=True)
        self.uploader.repo_entities = {
            'user': {
                'test.user': entities.FreeIPAUser(
                    'test.user',
                    {'firstName': 'Test', 'lastName': 'User',
                     'memberOf': {'group': ['group-one']}}, 'path')},
            'group': {'group-one': entities.FreeIPAUserGroup(
                'group-one', {}, 'path')},
            'sudorule': {'rule-one': entities.FreeIPASudoRule(
                'rule-one', {'options': ['!authenticate', '!requiretty'],
                             'memberUser': ['group-one']}, 'path')},
            'role': {},
            'privilege': {},
            'permission': {},
            'service': {},
            'hbacsvc': {},
            'hbacsvcgroup': {}
        }
        self.uploader.ipa_entities = {
            'group': {
                'group-one': entities.FreeIPAUserGroup(
                    'group-one', {'cn': ('group-one',),
                                  u'objectclass': (u'posixgroup',)}),
                'group-two': entities.FreeIPAUserGroup(
                    'group-two', {'cn': (u'group-two',)})},
            'user': dict(),
            'sudorule': dict(),
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader._prepare_push()
        assert len(self.uploader.commands) == 7
        assert [i.command for i in sorted(self.uploader.commands)] == [
            'sudorule_add', 'user_add', 'group_add_member',
            'sudorule_add_option', 'sudorule_add_option',
            'sudorule_add_user', 'group_del']

    def test_prepare_push_memberof_add_new_group(self):
        self._create_uploader(debug=True)
        self.uploader.repo_entities = {
            'user': {
                'test.user': entities.FreeIPAUser(
                    'test.user',
                    {'firstName': 'Test', 'lastName': 'User',
                     'memberOf': {'group': ['group-one']}}, 'path')},
            'group': {
                'group-one': entities.FreeIPAUserGroup(
                    'group-one', {}, 'path')}}
        self.uploader.ipa_entities = {
            'user': {
                'test.user': entities.FreeIPAUser('test.user', {
                    'uid': ('test.user',),
                    'givenname': (u'Test',), 'sn': (u'User',)})},
            'group': dict(),
            'role': dict(),
            'permission': dict(),
            'privilege': dict(),
            'service': dict(),
            'hbacsvc': dict(),
            'hbacsvcgroup': dict()}
        self.uploader._prepare_push()
        assert len(self.uploader.commands) == 2
        assert [i.command for i in sorted(self.uploader.commands)] == [
            'group_add', 'group_add_member']

    def test_prepare_del_commands(self):
        self.uploader.repo_entities = dict()
        self.uploader.ipa_entities = {
            'user': {
                'test.user': {'uid': ('test.user',)}
            }
        }
        self.uploader.commands = []
        self.uploader._prepare_del_commands()
        assert len(self.uploader.commands) == 1
        cmd = self.uploader.commands[0]
        assert cmd.command == 'user_del'
        assert cmd.description == 'user_del test.user ()'
        assert cmd.payload == {'uid': u'test.user'}

    def test_filter_deletion_commands(self):
        self.uploader.deletion_patterns = ['.+_add$']
        old_cmds = [
            tool.Command('user_add', {}, 'user1', 'user'),
            tool.Command('group_add_member', {}, 'group-one', 'group')]
        self.uploader.commands = old_cmds
        self.uploader._filter_deletion_commands()
        assert self.uploader.commands == old_cmds[1:]

    def test_add_command(self):
        cmd = tool.Command(
            'test_cmd', {'description': ('Test',)}, 'group1', 'cn')
        assert cmd.payload == {'cn': u'group1', 'description': u'Test'}
        for key in ('cn', 'description'):
            assert isinstance(cmd.payload[key], unicode)
        assert cmd.description == 'test_cmd group1 (description=Test)'

    def test_command_ordering(self):
        for i in ('user', 'group', 'hostgroup', 'hbacrule', 'sudorule'):
            assert tool.Command('%s_add' % i, {}, '', '') < tool.Command(
                '%s_add_whatever' % i, {}, '', '')

    def test_check_threshold(self):
        self._create_uploader(threshold=10)
        self.uploader.commands = [
            tool.Command('cmd%d' % i, {}, '', '') for i in range(1, 12)]
        self.uploader.ipa_entity_count = 120
        with LogCapture('IpaUploader', level=logging.DEBUG) as log:
            self.uploader._check_threshold()
        log.check(
            ('IpaUploader', 'DEBUG',
             '11 commands, 120 remote entities (9.17 %)'),
            ('IpaUploader', 'DEBUG', 'Threshold check passed'))

    def test_check_threshold_over_100(self):
        self._create_uploader(threshold=100)
        self.uploader.commands = [
            tool.Command('cmd%d' % i, {}, '', '') for i in range(1, 100)]
        self.uploader.ipa_entity_count = 10
        with LogCapture('IpaUploader', level=logging.DEBUG) as log:
            self.uploader._check_threshold()
        log.check(
            ('IpaUploader', 'DEBUG',
             '99 commands, 10 remote entities (100.00 %)'),
            ('IpaUploader', 'DEBUG', 'Threshold check passed'))

    def test_check_threshold_empty_ipa(self):
        self._create_uploader(threshold=10)
        self.uploader.commands = [
            tool.Command('cmd%d' % i, {}, '', '') for i in range(1, 12)]
        self.uploader.ipa_entity_count = 0
        with LogCapture('IpaUploader', level=logging.DEBUG) as log:
            with pytest.raises(tool.ManagerError) as exc:
                self.uploader._check_threshold()
        assert exc.value[0] == 'Threshold exceeded (100.00 % > 10 %), aborting'
        log.check(
            ('IpaUploader', 'DEBUG',
             '11 commands, 0 remote entities (100.00 %)'))

    def test_check_threshold_exceeded(self):
        self._create_uploader(threshold=10)
        self.uploader.commands = [
            tool.Command('cmd%d' % i, {}, '', '') for i in range(1, 12)]
        self.uploader.ipa_entity_count = 100
        with pytest.raises(tool.ManagerError) as exc:
            self.uploader._check_threshold()
        assert exc.value[0] == 'Threshold exceeded (11.00 % > 10 %), aborting'

    @log_capture('IpaUploader', level=logging.INFO)
    def test_push_dry_run_no_todo(self, captured_log):
        with mock.patch('%s.load_ipa_entities' % up_class):
            self.uploader.push()
        captured_log.check(
            ('IpaUploader', 'INFO', '0 commands to execute'),
            ('IpaUploader', 'INFO',
             'FreeIPA consistent with local config, nothing to do'))

    @log_capture('IpaUploader', level=logging.INFO)
    def test_push_dry_run(self, captured_log):
        self._create_uploader()
        tool.api.Command.__getitem__.side_effect = self._api_call
        self.uploader.commands = self._large_commands()
        with mock.patch('%s.load_ipa_entities' % up_class):
            with mock.patch('%s._prepare_push' % up_class):
                with mock.patch('%s._check_threshold' % up_class):
                    self.uploader.push()
        captured_log.check(
            ('IpaUploader', 'INFO', 'Would execute commands:'),
            ('IpaUploader', 'INFO', '- group_add group1 ()'),
            ('IpaUploader', 'INFO', '- group_add group2 ()'),
            ('IpaUploader', 'INFO', '- hbacrule_add rule1 ()'),
            ('IpaUploader', 'INFO', '- hostgroup_add group1 ()'),
            ('IpaUploader', 'INFO', '- sudorule_add rule1 ()'),
            ('IpaUploader', 'INFO', '- user_add user1 ()'),
            ('IpaUploader', 'INFO', '- user_add user2 ()'),
            ('IpaUploader', 'INFO',
             u'- group_add_member group1 (user=user1)'),
            ('IpaUploader', 'INFO',
             u'- group_add_member group1-users (user=user2)'),
            ('IpaUploader', 'INFO',
             u'- group_add_member group2 (group=group1)'),
            ('IpaUploader', 'INFO',
             u'- hbacrule_add_host rule1 (hostgroup=group1)'),
            ('IpaUploader', 'INFO',
             u'- hbacrule_add_user rule1 (group=group2)'),
            ('IpaUploader', 'INFO',
             u'- sudorule_add_host rule1 (hostgroup=group1)'),
            ('IpaUploader', 'INFO',
             u'- sudorule_add_user rule1 (group=group2)'))
        assert self.uploader.errs == []

    @log_capture('IpaUploader', level=logging.INFO)
    def test_push_no_todo(self, captured_log):
        self._create_uploader(force=True)
        with mock.patch('%s.load_ipa_entities' % up_class):
            self.uploader.push()
        captured_log.check(
            ('IpaUploader', 'INFO', '0 commands to execute'),
            ('IpaUploader', 'INFO',
             'FreeIPA consistent with local config, nothing to do'))
        assert self.uploader.commands == []

    def test_push_threshold_exceeded(self):
        self._create_uploader(force=True, threshold=10)
        self.uploader.ipa_entity_count = 100
        self.uploader.commands = [
            tool.Command('cmd%d' % i, {}, '', '') for i in range(1, 12)]
        with mock.patch('%s.load_ipa_entities' % up_class):
            with mock.patch('%s._prepare_push' % up_class):
                with pytest.raises(tool.ManagerError) as exc:
                    self.uploader.push()
        assert exc.value[0] == 'Threshold exceeded (11.00 % > 10 %), aborting'

    @log_capture('Command', level=logging.INFO)
    def test_push(self, captured_log):
        self._create_uploader(force=True, threshold=15)
        tool.api.Command.__getitem__.side_effect = self._api_call
        self.uploader.commands = self._large_commands()
        with mock.patch('%s._prepare_push' % up_class):
            with mock.patch('%s._check_threshold' % up_class):
                self.uploader.push()
        captured_log.check(
            ('Command', 'INFO', 'Executing group_add group1 ()'),
            ('Command', 'INFO', u'Added group "group1"'),
            ('Command', 'INFO', 'Executing group_add group2 ()'),
            ('Command', 'INFO', u'Added group "group2"'),
            ('Command', 'INFO', 'Executing hbacrule_add rule1 ()'),
            ('Command', 'INFO', u'Added hbacrule "rule1"'),
            ('Command', 'INFO', 'Executing hostgroup_add group1 ()'),
            ('Command', 'INFO', u'Added hostgroup "group1"'),
            ('Command', 'INFO', 'Executing sudorule_add rule1 ()'),
            ('Command', 'INFO', u'Added sudorule "rule1"'),
            ('Command', 'INFO', 'Executing user_add user1 ()'),
            ('Command', 'INFO', u'Added user "user1"'),
            ('Command', 'INFO', 'Executing user_add user2 ()'),
            ('Command', 'INFO', u'Added user "user2"'),
            ('Command', 'INFO',
             u'Executing group_add_member group1 (user=user1)'),
            ('Command', 'INFO',
             u'group_add_member group1 (user=user1) successful'),
            ('Command', 'INFO',
             u'Executing group_add_member group1-users (user=user2)'),
            ('Command', 'INFO',
             u'group_add_member group1-users (user=user2) successful'),
            ('Command', 'INFO',
             u'Executing group_add_member group2 (group=group1)'),
            ('Command', 'INFO',
             u'group_add_member group2 (group=group1) successful'),
            ('Command', 'INFO',
             u'Executing hbacrule_add_host rule1 (hostgroup=group1)'),
            ('Command', 'INFO',
             u'hbacrule_add_host rule1 (hostgroup=group1) successful'),
            ('Command', 'INFO',
             u'Executing hbacrule_add_user rule1 (group=group2)'),
            ('Command', 'INFO',
             u'hbacrule_add_user rule1 (group=group2) successful'),
            ('Command', 'INFO',
             u'Executing sudorule_add_host rule1 (hostgroup=group1)'),
            ('Command', 'INFO',
             u'sudorule_add_host rule1 (hostgroup=group1) successful'),
            ('Command', 'INFO',
             u'Executing sudorule_add_user rule1 (group=group2)'),
            ('Command', 'INFO',
             u'sudorule_add_user rule1 (group=group2) successful'))
        assert self.uploader.errs == []

    @log_capture('Command', level=logging.ERROR)
    def test_push_errors(self, captured_log):
        self._create_uploader(force=True, threshold=15)
        tool.api.Command.__getitem__.side_effect = (
            self._api_call_unreliable)
        self.uploader.commands = self._large_commands()
        with mock.patch('%s._prepare_push' % up_class):
            with mock.patch('%s._check_threshold' % up_class):
                with pytest.raises(tool.ManagerError) as exc:
                    self.uploader.push()
        assert exc.value[0] == 'There were 5 errors executing update'
        assert self.uploader.errs == [
            u"Error executing group_add_member group1 (user=user1):"
            " Error executing group_add_member: [u'- test: no such attr2']",
            u"Error executing group_add_member group1-users (user=user2):"
            " Error executing group_add_member: [u'- test: no such attr2']",
            u"Error executing group_add_member group2 (group=group1):"
            " Error executing group_add_member: [u'- test: no such attr2']",
            u"Error executing hbacrule_add_user rule1 (group=group2):"
            " Error executing hbacrule_add_user: [u'- test: no such attr2']",
            u"Error executing sudorule_add_user rule1 (group=group2):"
            " Error executing sudorule_add_user: [u'- test: no such attr2']"]
        captured_log.check(
            ('Command', 'ERROR',
             u'group_add_member group1 (user=user1) failed:'),
            ('Command', 'ERROR', u'- test: no such attr2'),
            ('Command', 'ERROR',
             u'group_add_member group1-users (user=user2) failed:'),
            ('Command', 'ERROR', u'- test: no such attr2'),
            ('Command', 'ERROR',
             u'group_add_member group2 (group=group1) failed:'),
            ('Command', 'ERROR', u'- test: no such attr2'),
            ('Command', 'ERROR',
             u'hbacrule_add_user rule1 (group=group2) failed:'),
            ('Command', 'ERROR', u'- test: no such attr2'),
            ('Command', 'ERROR',
             u'sudorule_add_user rule1 (group=group2) failed:'),
            ('Command', 'ERROR', u'- test: no such attr2'))

    def test_push_exceptions(self):
        self._create_uploader(force=True, threshold=15)
        tool.api.Command.__getitem__.side_effect = (
            self._api_call_execute_fail)
        self.uploader.commands = self._large_commands()
        with mock.patch('%s._prepare_push' % up_class):
            with mock.patch('%s._check_threshold' % up_class):
                with pytest.raises(tool.ManagerError) as exc:
                    self.uploader.push()
        assert exc.value[0] == 'There were 3 errors executing update'
        assert self.uploader.errs == [
            u'Error executing group_add_member group1 (user=user1):'
            ' Error executing group_add_member: Some error happened',
            u'Error executing group_add_member group1-users (user=user2):'
            ' Error executing group_add_member: Some error happened',
            u'Error executing group_add_member group2 (group=group1):'
            ' Error executing group_add_member: Some error happened']

    def test_push_invalid_command(self):
        self._create_uploader(force=True, threshold=15)
        tool.api.Command.__getitem__.side_effect = self._api_call
        self.uploader.commands = [tool.Command('invalid', {}, 'x', 'cn')]
        with mock.patch('%s._prepare_push' % up_class):
            with mock.patch('%s._check_threshold' % up_class):
                with pytest.raises(tool.ManagerError) as exc:
                    self.uploader.push()
        assert exc.value[0] == 'There were 1 errors executing update'
        assert self.uploader.errs == [
            'Error executing invalid x (): Non-existent command invalid']

    def _api_call_unreliable(self, command):
        try:
            return {
                'group_add_member': self._api_fail,
                'hbacrule_add_user': self._api_fail,
                'sudorule_add_user': self._api_fail
            }[command]
        except KeyError:
            return self._api_call(command)

    def _api_call_find_fail(self, command):
        if command.endswith('find'):
            return self._api_exc
        return self._api_call(command)

    def _api_call_execute_fail(self, command):
        if command == 'group_add_member':
            return self._api_exc
        return self._api_call(command)

    def _api_group_find(self, **kwargs):
        return {'result': [{'cn': ('group-one',)}]}

    def _api_rule_find(self, **kwargs):
        return {'result': [{'cn': ('rule-one',)}]}

    def _api_user_find(self, **kwargs):
        return {'result': [{'uid': ('user.one',)}]}

    def _api_user_add(self, **kwargs):
        return {'summary': u'Added user "%s"' % kwargs.get('uid')}

    def _api_add(self, name):
        def _func(**kwargs):
            return {'summary': u'Added %s "%s"' % (name, kwargs.get('cn'))}
        return _func

    def _api_nosummary(self, **kwargs):
        return {u'failed': {u'attr1': {'param1': (), 'param2': ()}}}

    def _api_fail(self, **kwargs):
        return {
            u'failed': {u'attr1': {'param1': ((u'test', u'no such attr2'),)}}}

    def _api_exc(self, **kwargs):
        raise Exception('Some error happened')

    def _large_commands(self):
        return [
            tool.Command('user_add', {}, 'user1', 'uid'),
            tool.Command('user_add', {}, 'user2', 'uid'),
            tool.Command('group_add', {}, 'group1', 'cn'),
            tool.Command('group_add', {}, 'group2', 'cn'),
            tool.Command('hostgroup_add', {}, 'group1', 'cn'),
            tool.Command('hbacrule_add', {}, 'rule1', 'cn'),
            tool.Command('sudorule_add', {}, 'rule1', 'cn'),
            tool.Command(
                'group_add_member', {'user': u'user1'}, 'group1', 'cn'),
            tool.Command(
                'group_add_member', {'group': u'group1'}, 'group2', 'cn'),
            tool.Command(
                'group_add_member', {'user': u'user2'}, 'group1-users', 'cn'),
            tool.Command(
                'hbacrule_add_user', {'group': u'group2'}, 'rule1', 'cn'),
            tool.Command(
                'hbacrule_add_host', {'hostgroup': u'group1'}, 'rule1', 'cn'),
            tool.Command(
                'sudorule_add_user', {'group': u'group2'}, 'rule1', 'cn'),
            tool.Command(
                'sudorule_add_host', {'hostgroup': u'group1'}, 'rule1', 'cn')
        ]


class TestIpaDownloader(TestIpaConnectorBase):
    def setup_method(self, method):
        with open(SETTINGS) as settings_file:
            self.settings = yaml.safe_load(settings_file)
        self._create_downloader()
        if method.func_name.startswith('test_dump_membership'):
            self.downloader.ipa_entities = {
                'user': {
                    'test.user': entities.FreeIPAUser('test.user', {
                        'uid': ('test.user',),
                        'givenname': (u'Test',), 'sn': (u'User',),
                        'memberof_group': ('group-two', 'group-one')}),
                    'user.two': entities.FreeIPAUser('user.two', {
                        'uid': ('user.two',),
                        'givenname': (u'User',), 'sn': (u'Two',)}),
                    'user.three': entities.FreeIPAUser('user.three', {
                        'uid': ('user.three',),
                        'givenname': (u'User',), 'sn': (u'Three',)}),
                }, 'group': {
                    'group-one': entities.FreeIPAUserGroup('group-one', {
                        'cn': ('group-one',),
                        'memberof_group': ('group-two',)}),
                    'group-two': entities.FreeIPAUserGroup('group-two', {
                        'cn': ('group-two',), 'member_group': ('group-one',),
                        'member_user': ('test.user',)})
                }, 'role': {
                    'role-one': entities.FreeIPARole('role-one', {
                        'cn': ('role-one',)})
                }, 'permission': {
                    'permission-one': entities.FreeIPAPermission(
                        'permission-one', {
                            'cn': ('permission-one',),
                            'member_privilege': ('privilege-one',)})
                }, 'privilege': {
                    'privilege-one': entities.FreeIPAPrivilege(
                        'privilege-one', {
                            'cn': ('privilege-one',),
                            'member_role': ('role-one',)})}}
        if 'pull' in method.func_name:
            self.downloader.ipa_entities, self.downloader.repo_entities = (
                self._pull_entities())

    def _create_downloader(self, **args):
        self.downloader = tool.IpaDownloader(
            settings=self.settings,
            parsed=args.get('parsed', {}),
            repo_path=args.get('repo_path', 'some_path'),
            dry_run=args.get('dry_run', False),
            add_only=args.get('add_only', False),
            pull_types=args.get('pull_types', ['user']))

    def test_dump_membership_user(self):
        user = self.downloader.ipa_entities['user']['test.user']
        assert self.downloader._dump_membership(user) == {
            'memberOf': {'group': ['group-two']}}
        user2 = self.downloader.ipa_entities['user']['user.two']
        assert self.downloader._dump_membership(user2) is None

    def test_dump_membership_group(self):
        group1 = self.downloader.ipa_entities['group']['group-one']
        assert self.downloader._dump_membership(group1) == {
            'memberOf': {'group': ['group-two']}}
        group2 = self.downloader.ipa_entities['group']['group-two']
        assert self.downloader._dump_membership(group2) is None

    def test_dump_membership_rule(self):
        rule1 = entities.FreeIPAHBACRule('rule-one', {'description': 'test'})
        assert self.downloader._dump_membership(rule1) is None
        data = {
            u'memberhost_hostgroup': (u'group-two',),
            u'memberuser_group': (u'group-two',),
            u'ipasudoopt': (u'!authenticate',),
            u'description': (u'Sample sudo rule two',)}
        rule2 = entities.FreeIPAHBACRule('rule-two', data)
        assert self.downloader._dump_membership(rule2) == {
            'memberHost': ['group-two'], 'memberUser': ['group-two']}

    def test_generate_filename(self):
        self._create_downloader(repo_path='entities')
        self.downloader.repo_entities['user'] = {}
        user = entities.FreeIPAUser(
            't.u', {'firstName': 'T', 'lastName': 'U'}, 'path')
        user.path = None
        self.downloader._generate_filename(user)
        assert user.path == 'entities/users/t_u.yaml'

    def test_generate_filename_already_has_one(self):
        user = self._filename_sample_user()
        assert user.path == 'entities/users/test_user.yaml'
        with pytest.raises(tool.ConfigError) as exc:
            self.downloader._generate_filename(user)
        assert exc.value[0] == (
            'test already has filepath (entities/users/test_user.yaml)')

    def test_generate_filename_used(self):
        self._create_downloader(repo_path='entities')
        user = self._filename_sample_user()
        self.downloader.repo_entities['user'] = {user.name: user}
        user2 = entities.FreeIPAUser(
            'test.user', {'firstName': 'Test', 'lastName': 'User'}, 'path')
        user2.path = None
        with pytest.raises(tool.ConfigError) as exc:
            self.downloader._generate_filename(user2)
        assert exc.value[0] == 'users/test_user.yaml filename already used'

    def test_pull_dry_run(self):
        self._create_downloader(dry_run=True, add_only=True)
        self.downloader.ipa_entities, self.downloader.repo_entities = (
            self._pull_entities())
        with mock.patch('%s.IpaDownloader.load_ipa_entities' % modulename):
            with LogCapture('IpaDownloader', level=logging.INFO) as log:
                self.downloader.pull()
        assert sorted([(r.levelno, r.msg % r.args) for r in log.records]) == [
            (20, 'Would update user test.user')]

    def test_pull_dry_run_enable_deletion(self):
        self._create_downloader(dry_run=True)
        self.downloader.ipa_entities, self.downloader.repo_entities = (
            self._pull_entities())
        with mock.patch('%s.IpaDownloader.load_ipa_entities' % modulename):
            with LogCapture('IpaDownloader', level=logging.INFO) as log:
                self.downloader.pull()
        assert sorted([(r.levelno, r.msg % r.args) for r in log.records]) == [
            (20, 'Would delete user user.two'),
            (20, 'Would update user test.user')]

    def test_pull_add_only(self):
        self._create_downloader(dry_run=False, add_only=True)
        self.downloader.ipa_entities, self.downloader.repo_entities = (
            self._pull_entities())
        output = dict()
        with mock.patch('yaml.dump', _mock_dump(output, yaml.dump)):
            with mock.patch('%s.IpaDownloader.load_ipa_entities' % modulename):
                with mock.patch('%s.os.unlink' % modulename) as mock_delete:
                    with mock.patch('__builtin__.open'):
                        self.downloader.pull()
        assert output == {
            'test.user': ('---\n'
                          'test.user:\n'
                          '  firstName: Test\n'
                          '  lastName: User\n'
                          '  memberOf:\n'
                          '    group:\n'
                          '      - group-one\n')}
        mock_delete.assert_not_called()

    def test_pull(self):
        output = dict()
        with mock.patch('yaml.dump', _mock_dump(output, yaml.dump)):
            with mock.patch('__builtin__.open'):
                with mock.patch('%s.os.unlink' % modulename) as mock_delete:
                    with mock.patch(
                            '%s.IpaDownloader.load_ipa_entities' % modulename):
                        self.downloader.pull()
        assert output == {
            'test.user': ('---\n'
                          'test.user:\n'
                          '  firstName: Test\n'
                          '  lastName: User\n'
                          '  memberOf:\n'
                          '    group:\n'
                          '      - group-one\n')}
        mock_delete.assert_called_with('user_two.yaml')

    def _pull_entities(self):
        remote = {
            'user': {'test.user': entities.FreeIPAUser('test.user', {
                'uid': ('test.user',),
                'givenname': (u'Test',), 'sn': (u'User',),
                'memberof_group': (u'group-one',)})},
            'group': {
                'group-one': entities.FreeIPAUserGroup('group-one', {
                    'cn': ('group-one',), 'description': ('test',),
                    'member_user': ('test.user',),
                    u'objectclass': (u'posixgroup',)}),
                'group-two': entities.FreeIPAUserGroup('group-two', {
                    'cn': ('group-two',)})},
            'hbacrule': {}, 'sudorule': {},
            'hostgroup': {
                'group-one': entities.FreeIPAHostGroup('group-one', {
                    'cn': ('group-one',), 'description': ('test',),
                    'member_user': ('test.user',)})},
            'permission': {},
            'privilege': {},
            'role': {},
            'service': {},
            'hbacsvc': {},
            'hbacsvcgroup': {}}
        local = {
            'user': {
                'test.user': entities.FreeIPAUser(
                    'test.user',
                    {'firstName': 'Test', 'lastName': 'user'}, 'test-user'),
                'user.two': entities.FreeIPAUser(
                    'user.two',
                    {'firstName': 'User', 'lastName': 'Two'}, 'user-two')},
            'group': {
                'group-one': entities.FreeIPAUserGroup(
                    'group-one', {'description': 'test',
                                  'posix': False}, 'path'),
                'group-two': entities.FreeIPAUserGroup(
                    'group-two',
                    {'memberOf': {'group': ['group-one']}}, 'path')},
            'hbacrule': {
                'rule-one': entities.FreeIPAHBACRule(
                    'rule-one', {'description': 'test'}, 'rule-one')},
                'sudorule': {}, 'hostgroup': {},
            'permission': {},
            'privilege': {},
            'role': {},
            'service': {},
            'hbacsvc': {},
            'hbacsvcgroup': {}}
        return (remote, local)

    def _filename_sample_user(self):
        return entities.FreeIPAUser(
            'test', {'firstName': 'Test', 'lastName': 'User'},
            'entities/users/test_user.yaml')
