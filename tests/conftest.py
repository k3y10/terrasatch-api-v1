"""Register all SQLAlchemy model modules for isolated test collection.

Many unit tests create a temporary SQLite schema directly from Base.metadata.
Importing the complete model set here makes those tests independent of pytest
collection order and mirrors the model registration used by Alembic.
"""

from terrasatch.actions import models as action_models
from terrasatch.auth import models as auth_models
from terrasatch.billing import models as billing_models
from terrasatch.edge import models as edge_models
from terrasatch.identity import models as identity_models
from terrasatch.integrations import models as integration_models
from terrasatch.masterdata import models as masterdata_models
from terrasatch.organizations import models as organization_models
from terrasatch.outbound import models as outbound_models
from terrasatch.radio import models as radio_models
from terrasatch.workspace import models as workspace_models

_MODEL_MODULES = (
    action_models,
    auth_models,
    billing_models,
    edge_models,
    identity_models,
    integration_models,
    masterdata_models,
    organization_models,
    outbound_models,
    radio_models,
    workspace_models,
)

assert _MODEL_MODULES
