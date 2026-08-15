<?php

namespace OPNsense\WanQuota\Api;

use OPNsense\Base\ApiMutableModelControllerBase;

class SettingsController extends ApiMutableModelControllerBase
{
    protected static $internalModelClass = '\\OPNsense\\WanQuota\\WanQuota';
    protected static $internalModelName = 'wanquota';
    protected static $internalSaveRequiresAdmin = true;
}

