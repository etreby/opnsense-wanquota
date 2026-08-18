<?php

namespace OPNsense\WanQuota;

class GeneralController extends \OPNsense\Base\IndexController
{
    /**
     * The settings are presented as a wizard rather than one form.
     *
     * Seventy-four fields in a single flat list gave no sense of what mattered
     * first or which settings could change how traffic flows. Each step is its own
     * form definition so the grouping lives in the definitions rather than in
     * markup, and every field carries help text.
     */
    public function indexAction()
    {
        foreach (['basics', 'providers', 'reporting', 'alerts', 'intelligence', 'enforcement'] as $step) {
            $this->view->{'wizard' . ucfirst($step)} = $this->getForm('wizard_' . $step);
        }
        $this->view->pick('OPNsense/WanQuota/general');
    }
}
