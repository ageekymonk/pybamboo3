# -*- coding: utf-8 -*-
#

class BambooError(Exception):
    pass

class BambooAuthenticationError(BambooError):
    pass

class BambooConnectionError(BambooError):
    pass

class BambooOperationError(BambooError):
    pass

class BambooListError(BambooOperationError):
    pass

class BambooGetError(BambooOperationError):
    pass

class BambooCreateError(BambooOperationError):
    pass

class BambooUpdateError(BambooOperationError):
    pass

class BambooDeleteError(BambooOperationError):
    pass

class BambooCancelError(BambooOperationError):
    pass

class BambooRetryError(BambooOperationError):
    pass
