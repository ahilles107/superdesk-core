# -*- coding: utf-8; -*-
#
# This file is part of Superdesk.
#
# Copyright 2013, 2014 Sourcefabric z.u. and contributors.
#
# For the full copyright and license information, please see the
# AUTHORS and LICENSE files distributed with this source code, or
# at https://www.sourcefabric.org/superdesk/license

import logging
from superdesk.activity import add_activity, ACTIVITY_UPDATE
from superdesk.services import BaseService
from superdesk import get_resource_service
from superdesk.errors import SuperdeskApiError
from superdesk.notification import push_notification
from superdesk.utils import compare_preferences
import superdesk

logger = logging.getLogger(__name__)

from superdesk.resource import Resource


class RolesResource(Resource):
    schema = {
        'name': {
            'type': 'string',
            'required': True,
            'nullable': False,
            'empty': False,
            'iunique': True
        },
        'description': {
            'type': 'string'
        },
        'privileges': {
            'type': 'dict'
        },
        'is_default': {
            'type': 'boolean'
        },
    }

    privileges = {'POST': 'roles', 'DELETE': 'roles', 'PATCH': 'roles'}


class RolesService(BaseService):

    def on_update(self, updates, original):
        if updates.get('is_default'):
            # if we are updating the role that is already default that is OK
            if original.get('is_default'):
                return
            self.remove_old_default()

    def on_create(self, docs):
        for doc in docs:
            # if this new one is default need to remove the old default
            if doc.get('is_default'):
                self.remove_old_default()

    def on_delete(self, docs):
        if docs.get('is_default'):
            raise SuperdeskApiError.forbiddenError('Cannot delete the default role')
        # check if there are any users in the role
        user = get_resource_service('users').find_one(req=None, role=docs.get('_id'))
        if user:
            raise SuperdeskApiError.forbiddenError('Cannot delete the role, it still has users in it!')

    def remove_old_default(self):
        # see if there is already a default role and set it to no longer default
        role_id = self.get_default_role_id()
        # make it no longer default
        if role_id:
            role = self.find_one(req=None, is_default=True)
            get_resource_service('roles').update(role_id, {"is_default": False}, role)

    def get_default_role_id(self):
        role = self.find_one(req=None, is_default=True)
        return role.get('_id') if role is not None else None

    def on_updated(self, updates, role):
        self.__send_notification(updates, role)

    def __send_notification(self, updates, role):
        role_id = role['_id']

        role_users = superdesk.get_resource_service('users').get_users_by_role(role_id)
        notified_users = [user['_id'] for user in role_users]

        if 'privileges' in updates:
            added, removed, modified = compare_preferences(role.get('privileges', {}), updates['privileges'])
            if len(removed) > 0 or (1, 0) in modified.values():
                push_notification('role_privileges_revoked', updated=1, role_id=str(role_id))
            if len(added) > 0:
                add_activity(ACTIVITY_UPDATE,
                             'role {{role}} is granted new privileges: Please re-login.',
                             self.datasource,
                             notify=notified_users,
                             role=role.get('name'))
        else:
            push_notification('role', updated=1, user_id=str(role_id))
