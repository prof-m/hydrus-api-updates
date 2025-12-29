from hydrus.core import HydrusConstants as HC
from hydrus.core import HydrusExceptions
from hydrus.core import HydrusTags
from hydrus.core.networking import HydrusNetworkVariableHandling
from hydrus.core.networking import HydrusServerRequest
from hydrus.core.networking import HydrusServerResources

from hydrus.client import ClientAPI
from hydrus.client import ClientGlobals as CG
from hydrus.client.metadata import ClientContentUpdates
from hydrus.client.networking.api import ClientLocalServerCore
from hydrus.client.networking.api import ClientLocalServerResources


_ACTION_NAME_TO_CONTENT_ACTION = {
    'add' : HC.CONTENT_UPDATE_ADD,
    'delete' : HC.CONTENT_UPDATE_DELETE,
    'pend' : HC.CONTENT_UPDATE_PEND,
    'petition' : HC.CONTENT_UPDATE_PETITION,
    'rescind_pend' : HC.CONTENT_UPDATE_RESCIND_PEND,
    'rescind_petition' : HC.CONTENT_UPDATE_RESCIND_PETITION
}


class HydrusResourceClientAPIRestrictedManageTags( ClientLocalServerResources.HydrusResourceClientAPIRestricted ):
    
    def _CheckAPIPermissions( self, request: HydrusServerRequest.HydrusRequest ):
        
        request.client_api_permissions.CheckPermission( ClientAPI.CLIENT_API_PERMISSION_ADD_TAGS )
        
    

class HydrusResourceClientAPIRestrictedManageTagRelationships( ClientLocalServerResources.HydrusResourceClientAPIRestricted ):
    
    def _CheckAPIPermissions( self, request: HydrusServerRequest.HydrusRequest ):
        
        request.client_api_permissions.CheckPermission( ClientAPI.CLIENT_API_PERMISSION_MANAGE_TAG_RELATIONSHIPS )
        
    

class HydrusResourceClientAPIRestrictedManageTagsGetTags( HydrusResourceClientAPIRestrictedManageTags ):
    
    def _threadDoGETJob( self, request: HydrusServerRequest.HydrusRequest ):
        
        tags = request.parsed_request_args.GetValue( 'tags', list, expected_list_type = str, default_value = [] )
        tag_service_key = request.parsed_request_args.GetValue( 'tag_service_key', bytes, default_value = None )
        
        if tag_service_key is not None:
            
            ClientLocalServerCore.CheckTagService( tag_service_key )
        
        tag_info = CG.client_controller.Read( 'tags_info', tags, tag_service_key )
        
        body = ClientLocalServerCore.Dumps( { 'tags' : tag_info }, request.preferred_mime )
        
        return HydrusServerResources.ResponseContext( 200, mime = request.preferred_mime, body = body )
        
    

class HydrusResourceClientAPIRestrictedManageTagsCreateTags( HydrusResourceClientAPIRestrictedManageTags ):
    
    def _threadDoPOSTJob( self, request: HydrusServerRequest.HydrusRequest ):
        
        tag_service_key = request.parsed_request_args.GetValue( 'tag_service_key', bytes )
        
        ClientLocalServerCore.CheckTagService( tag_service_key )
        
        tags = request.parsed_request_args.GetValue( 'tags', list, expected_list_type = str, default_value = [] )
        
        if len( tags ) == 0:
            
            raise HydrusExceptions.BadRequestException( 'No tags were provided!' )
            
        
        results = CG.client_controller.WriteSynchronous( 'create_tags', tag_service_key, tags )
        
        body = ClientLocalServerCore.Dumps( { 'tags' : results }, request.preferred_mime )
        
        return HydrusServerResources.ResponseContext( 200, mime = request.preferred_mime, body = body )
        
    

class HydrusResourceClientAPIRestrictedManageTagsGetRelationships( HydrusResourceClientAPIRestrictedManageTagRelationships ):
    
    def _threadDoGETJob( self, request: HydrusServerRequest.HydrusRequest ):
        
        tag_service_key = request.parsed_request_args.GetValue( 'tag_service_key', bytes )
        
        ClientLocalServerCore.CheckTagService( tag_service_key )
        
        tags = request.parsed_request_args.GetValue( 'tags', list, expected_list_type = str, default_value = None )
        
        if tags is None:
            
            raise HydrusExceptions.BadRequestException( 'Tags are required for this request!' )
            
        
        clean_tags = _CleanTagsPreserveOrder( tags )
        
        if len( clean_tags ) == 0:
            
            raise HydrusExceptions.BadRequestException( 'No tags were provided!' )
            
        
        include_pending = request.parsed_request_args.GetValue( 'include_pending', bool, default_value = False )
        
        tags_out = {}
        
        for tag in clean_tags:
            
            siblings = CG.client_controller.Read( 'tag_siblings', tag_service_key, [ tag ], include_pending )
            parents = CG.client_controller.Read( 'tag_parents', tag_service_key, [ tag ], include_pending )
            
            siblings_out = _ConvertStatusDictToDisplay( siblings )
            parents_out = _ConvertStatusDictToDisplay( parents )
            
            tags_out[ tag ] = {
                'tag_siblings' : _CollapseSiblingPairs( tag, siblings_out ),
                'tag_parents' : _CollapseParentPairs( tag, parents_out )
            }
        
        body = ClientLocalServerCore.Dumps( tags_out, request.preferred_mime )
        
        return HydrusServerResources.ResponseContext( 200, mime = request.preferred_mime, body = body )
        
    

class HydrusResourceClientAPIRestrictedManageTagsSetRelationships( HydrusResourceClientAPIRestrictedManageTagRelationships ):
    
    def _threadDoPOSTJob( self, request: HydrusServerRequest.HydrusRequest ):
        
        tag_service_key = request.parsed_request_args.GetValue( 'tag_service_key', bytes )
        
        service = ClientLocalServerCore.CheckTagService( tag_service_key )
        
        default_reason = request.parsed_request_args.GetValue( 'reason', str, default_value = 'Set by Client API' )
        
        siblings_actions = request.parsed_request_args.GetValue( 'tag_siblings', dict, default_value = {} )
        parents_actions = request.parsed_request_args.GetValue( 'tag_parents', dict, default_value = {} )
        
        content_update_package = ClientContentUpdates.ContentUpdatePackage()
        
        if len( siblings_actions ) > 0:
            
            content_updates = _BuildContentUpdatesFromPairs( siblings_actions, service, HC.CONTENT_TYPE_TAG_SIBLINGS, default_reason )
            
            content_update_package.AddContentUpdates( tag_service_key, content_updates )
            
        
        if len( parents_actions ) > 0:
            
            content_updates = _BuildContentUpdatesFromPairs( parents_actions, service, HC.CONTENT_TYPE_TAG_PARENTS, default_reason )
            
            content_update_package.AddContentUpdates( tag_service_key, content_updates )
            
        
        if not content_update_package.HasContent():
            
            raise HydrusExceptions.BadRequestException( 'No relationship actions were given!' )
            
        
        CG.client_controller.WriteSynchronous( 'content_updates', content_update_package )
        
        return HydrusServerResources.ResponseContext( 200 )
        
    

def _ConvertStatusDictToDisplay( statuses_to_pairs: dict ) -> dict:
    
    status_key_lookup = {
        HC.CONTENT_STATUS_CURRENT : 'current',
        HC.CONTENT_STATUS_PENDING : 'pending',
        HC.CONTENT_STATUS_PETITIONED : 'petitioned',
        HC.CONTENT_STATUS_DELETED : 'deleted'
    }
    
    statuses_out = { status_key : [] for status_key in status_key_lookup.values() }
    
    for ( status, pairs ) in statuses_to_pairs.items():
        
        if status not in status_key_lookup:
            
            continue
            
        
        statuses_out[ status_key_lookup[ status ] ] = sorted( list( pairs ) )
        
    
    return statuses_out


def _CollapseSiblingPairs( tag: str, statuses_to_pairs: dict ) -> dict:
    
    statuses_out = {}
    
    for ( status, pairs ) in statuses_to_pairs.items():
        
        related_tags = set()
        
        for ( bad_tag, good_tag ) in pairs:
            
            if bad_tag == tag:
                
                related_tags.add( good_tag )
                
            elif good_tag == tag:
                
                related_tags.add( bad_tag )
            
        
        statuses_out[ status ] = sorted( related_tags )
        
    
    return statuses_out
    

def _CollapseParentPairs( tag: str, statuses_to_pairs: dict ) -> dict:
    
    statuses_out = {}
    
    for ( status, pairs ) in statuses_to_pairs.items():
        
        parent_tags = { parent_tag for ( child_tag, parent_tag ) in pairs if child_tag == tag }
        
        statuses_out[ status ] = sorted( parent_tags )
        
    
    return statuses_out
    

def _CleanTagsPreserveOrder( tags ) -> list:
    
    clean_tags = []
    seen_tags = set()
    
    for tag in tags:
        
        if tag is None:
            
            continue
            
        
        try:
            
            clean_tag = HydrusTags.CleanTag( tag )
            HydrusTags.CheckTagNotEmpty( clean_tag )
            
        except HydrusExceptions.TagSizeException:
            
            continue
            
        
        if clean_tag in seen_tags:
            
            continue
            
        
        seen_tags.add( clean_tag )
        clean_tags.append( clean_tag )
        
    
    return clean_tags
    

def _BuildContentUpdatesFromPairs( actions_to_pairs: dict, service, content_type: int, default_reason: str ):
    
    content_updates = []
    
    for ( action_name, pairs ) in actions_to_pairs.items():
        
        HydrusNetworkVariableHandling.TestVariableType( 'action', action_name, str )
        
        if action_name not in _ACTION_NAME_TO_CONTENT_ACTION:
            
            raise HydrusExceptions.BadRequestException( f'Unrecognised action "{action_name}"!' )
            
        
        content_action = _ACTION_NAME_TO_CONTENT_ACTION[ action_name ]
        
        if service.GetServiceType() == HC.LOCAL_TAG:
            
            if content_action not in ( HC.CONTENT_UPDATE_ADD, HC.CONTENT_UPDATE_DELETE ):
                
                raise HydrusExceptions.BadRequestException( 'For local tag services, only add/delete actions are valid.' )
                
            
        else:
            
            if content_action in ( HC.CONTENT_UPDATE_ADD, HC.CONTENT_UPDATE_DELETE ):
                
                raise HydrusExceptions.BadRequestException( 'For repository tag services, you must pend/petition/rescind, not add/delete.' )
                
            
        
        HydrusNetworkVariableHandling.TestVariableType( 'pairs', pairs, list )
        
        for pair in pairs:
            
            reason = default_reason
            
            if not HydrusNetworkVariableHandling.IsJSONable( pair ):
                
                continue
                
            
            if isinstance( pair, ( list, tuple ) ):
                
                if len( pair ) == 2:
                    
                    ( first_tag, second_tag ) = pair
                    
                elif len( pair ) == 3:
                    
                    ( first_tag, second_tag, reason ) = pair
                    
                else:
                    
                    continue
                    
                
            else:
                
                continue
                
            
            try:
                
                first_tag = HydrusTags.CleanTag( first_tag )
                second_tag = HydrusTags.CleanTag( second_tag )
                
            except Exception as e:
                
                raise HydrusExceptions.BadRequestException( f'Problem cleaning tags "{pair}": {e}' )
                
            
            pair_tuple = ( first_tag, second_tag )
            
            if content_action in ( HC.CONTENT_UPDATE_PEND, HC.CONTENT_UPDATE_PETITION ):
                
                content_update = ClientContentUpdates.ContentUpdate( content_type, content_action, pair_tuple, reason = reason )
                
            else:
                
                content_update = ClientContentUpdates.ContentUpdate( content_type, content_action, pair_tuple )
                
            
            content_updates.append( content_update )
            
        
    
    return content_updates
