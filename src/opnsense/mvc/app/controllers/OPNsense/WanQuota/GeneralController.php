<?php

namespace OPNsense\WanQuota;

class GeneralController extends \OPNsense\Base\IndexController
{
    public function indexAction()
    {
        $this->view->generalForm = $this->getForm('general');
        $this->view->pick('OPNsense/WanQuota/general');
    }
}

