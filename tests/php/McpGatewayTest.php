<?php
/**
 * Plain-PHP tests for McpGateway. No framework, no PHPUnit: the point is that
 * CI already has a php binary, so this logic can be covered where previously
 * only `php -l` ran over it.
 */

require_once __DIR__ . '/../../src/opnsense/mvc/app/library/OPNsense/WanQuota/McpGateway.php';

use OPNsense\WanQuota\McpGateway;

$failures = [];
$checks = 0;

function check(string $name, $actual, $expected): void
{
    global $failures, $checks;
    $checks++;
    if ($actual !== $expected) {
        $failures[] = sprintf(
            "%s\n    expected: %s\n    actual:   %s",
            $name,
            var_export($expected, true),
            var_export($actual, true)
        );
    }
}

// --- client address validation -------------------------------------------------
check('LAN IPv4 accepted', McpGateway::isValidClient('192.168.1.32'), true);
check('IPv6 accepted', McpGateway::isValidClient('fd00::5'), true);
check('loopback accepted', McpGateway::isValidClient('127.0.0.1'), true);
check('hostname rejected', McpGateway::isValidClient('firewall.local'), false);
check('empty rejected', McpGateway::isValidClient(''), false);
check('null rejected', McpGateway::isValidClient(null), false);
check('array rejected', McpGateway::isValidClient(['192.168.1.1']), false);
check('injection attempt rejected', McpGateway::isValidClient("192.168.1.1; rm -rf /"), false);

// --- body encoding -------------------------------------------------------------
$body = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}';
$encoded = McpGateway::encodeBody($body);
check('base64 round trips', base64_decode($encoded), $body);
check('base64 is a single line', strpos($encoded, "\n"), false);

// --- fault shaping -------------------------------------------------------------
$fault = json_decode(McpGateway::fault(-32600, 'POST required'), true);
check('fault is jsonrpc 2.0', $fault['jsonrpc'], '2.0');
check('fault id is null', $fault['id'], null);
check('fault code preserved', $fault['error']['code'], -32600);
check('fault message preserved', $fault['error']['message'], 'POST required');

// --- interpret: success passes the payload through verbatim --------------------
// This is the regression that a real MCP client caught: decoding and re-encoding
// turns "properties":{} into "properties":[], which clients reject.
$withEmptyObject = '{"jsonrpc":"2.0","id":1,"result":{"tools":[{"inputSchema":{"type":"object","properties":{}}}]}}';
$result = McpGateway::interpret($withEmptyObject);
check('success is classified as json', $result['kind'], McpGateway::KIND_JSON);
check('success status is 200', $result['status'], 200);
check('empty object survives verbatim', $result['body'], $withEmptyObject);
check('empty object is not turned into a list', strpos($result['body'], '"properties":[]'), false);
check('empty object is still an object', strpos($result['body'], '"properties":{}') !== false, true);

// --- interpret: notification -> 202 with no body -------------------------------
$notification = McpGateway::interpret('{"_notification":true}');
check('notification classified', $notification['kind'], McpGateway::KIND_NOTIFICATION);
check('notification status is 202', $notification['status'], 202);
check('notification body is empty', $notification['body'], '');

// --- interpret: unusable backend output ----------------------------------------
foreach (['', 'not json at all', 'null', '"a string"'] as $bad) {
    $broken = McpGateway::interpret($bad);
    check("backend output " . var_export($bad, true) . " is a fault", $broken['kind'], McpGateway::KIND_FAULT);
    $decoded = json_decode($broken['body'], true);
    check("fault code for " . var_export($bad, true), $decoded['error']['code'], -32603);
}

// A JSON array is valid JSON and decodes to an array, so it is passed through
// rather than faulted; assert the actual behaviour rather than assuming.
check('json array is passed through', McpGateway::interpret('[]')['kind'], McpGateway::KIND_JSON);

// --- report --------------------------------------------------------------------
if ($failures) {
    fwrite(STDERR, sprintf("McpGateway: %d/%d checks FAILED\n\n", count($failures), $checks));
    foreach ($failures as $f) {
        fwrite(STDERR, "  - " . $f . "\n\n");
    }
    exit(1);
}
fwrite(STDOUT, sprintf("McpGateway: %d checks passed\n", $checks));
