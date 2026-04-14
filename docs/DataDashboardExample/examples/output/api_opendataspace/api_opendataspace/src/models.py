from pydantic import BaseModel
from typing import Optional, List, Any


class StandardError(BaseModel):
    
    
    code: int = None
    
    message: str = None
    
    


class StandardBadRequest(BaseModel):
    
    
    code: int = None
    
    message: str = None
    
    


class StandardOkEmptyResponse(BaseModel):
    
    
    code: int = None
    
    message: str = None
    
    data: str = None
    
    


class StandardListResponse(BaseModel):
    
    
    data: List[Any] = None
    
    code: int = None
    
    message: str = None
    
    


class StandardResponse(BaseModel):
    
    
    data: str = None
    
    code: int = None
    
    message: str = None
    
    


class UserEmail(BaseModel):
    
    pass
    


class UserPassword(BaseModel):
    
    pass
    


class Language(BaseModel):
    
    
    name: str = None
    
    code: str = None
    
    


class UserCredentials(BaseModel):
    
    
    email: str = None
    
    password: str = None
    
    


class UserCredentialsRecovery(BaseModel):
    
    
    email: str = None
    
    


class UserConfig(BaseModel):
    
    
    language: str = None
    
    


class RegisterUserRequest(BaseModel):
    
    pass
    


class Organization(BaseModel):
    
    
    name: str = None
    
    type: str = None
    
    description: str = None
    
    connector: str = None
    
    


class ModifyOrganization(BaseModel):
    
    pass
    


class Connector(BaseModel):
    
    
    host: str = None
    
    token: str = None
    
    is_virtual: bool = None
    
    organization_id: str = None
    
    


class ProfileRolesBody(BaseModel):
    
    
    roles: List[Any] = None
    
    


class SetDomainsBody(BaseModel):
    
    
    domain_ids: List[Any] = None
    
    


class DataSpace(BaseModel):
    
    
    id: str = None
    
    name: str = None
    
    description: str = None
    
    published: bool = None
    
    


class Catalog(BaseModel):
    
    
    id: str = None
    
    participant_id: str = None
    
    originator: str = None
    
    


class Domain(BaseModel):
    
    
    id: str = None
    
    name: str = None
    
    description: str = None
    
    organization_id: str = None
    
    


class ModifyDomain(BaseModel):
    
    pass
    


class RolesBody(BaseModel):
    
    pass
    


class UserInvitation(BaseModel):
    
    
    user_id: str = None
    
    


class NewUserInvitation(BaseModel):
    
    
    email: str = None
    
    roles: str = None
    
    


class NewUserAcceptInvitation(BaseModel):
    
    
    email: str = None
    
    status: str = None
    
    roles: str = None
    
    


class InvitationStatus(BaseModel):
    
    pass
    


class InvitationType(BaseModel):
    
    pass
    


class JoinRequest(BaseModel):
    
    
    user_id: str = None
    
    email: str = None
    
    


class UpdJoinRequest(BaseModel):
    
    
    status: str = None
    
    roles: str = None
    
    


class Invitation(BaseModel):
    
    
    id: str = None
    
    type: str = None
    
    status: str = None
    
    domain_ids: List[Any] = None
    
    


class DeveloperPortal(BaseModel):
    
    
    id: str = None
    
    organization_id: str = None
    
    environment_id: str = None
    
    access_id: str = None
    
    name: str = None
    
    description: str = None
    
    active: bool = None
    
    


class ModifyDeveloperPortalStatus(BaseModel):
    
    
    active: bool = None
    
    


class Environment(BaseModel):
    
    
    id: str = None
    
    organization_id: str = None
    
    name: str = None
    
    description: str = None
    
    


class ModifyEnvironment(BaseModel):
    
    pass
    


class CreateConnectorDataSpace(BaseModel):
    
    
    name: str = None
    
    description: str = None
    
    


class CreateCatalog(BaseModel):
    
    
    name: str = None
    
    description: str = None
    
    


class UpdateCatalog(BaseModel):
    
    
    name: str = None
    
    description: str = None
    
    


class CreateAsset(BaseModel):
    
    
    at_context: str = None
    
    at_id: str = None
    
    dataAddress: str = None
    
    privateProperties: str = None
    
    properties: str = None
    
    


class Asset(BaseModel):
    
    
    at_context: str = None
    
    at_id: str = None
    
    at_type: str = None
    
    createdAt: str = None
    
    


class CreatePolicy(BaseModel):
    
    
    id: str = None
    
    type: str = None
    
    


class Policy(BaseModel):
    
    
    at_type: str = None
    
    at_id: str = None
    
    createdAt: str = None
    
    at_context: str = None
    
    


class CreateContract(BaseModel):
    
    
    accessPolicyId: str = None
    
    contractPolicyId: str = None
    
    assetsSelector: List[Any] = None
    
    


class CreateConnectorCatalog(BaseModel):
    
    
    counter_party_did: str = None
    
    counter_party_address: str = None
    
    


class CreateContractNegotiation(BaseModel):
    
    
    assigner: str = None
    
    counter_party_address: str = None
    
    


class ContractNegotiation(BaseModel):
    
    
    at_context: str = None
    
    at_id: str = None
    
    at_type: str = None
    
    createdAt: str = None
    
    


