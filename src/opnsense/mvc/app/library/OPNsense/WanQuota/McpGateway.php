<?php

namespace OPNsense\WanQuota;

/**
 * Transport logic for the MCP endpoint, with no framework dependency.
 *
 * It lives apart from the controller so it can be tested. CI only runs `php -l`
 * over the controllers, which proves they parse and nothing else; the base64
 * wrapping, the client-address check and the response shaping are the parts that
 * can be wrong while still parsing, and one of them shipped broken before.
 */
class McpGateway
{
    /** Response shapes returned by interpret(). */
    public const KIND_JSON = 'json';
    public const KIND_NOTIFICATION = 'notification';
    public const KIND_FAULT = 'fault';

    /**
     * Only a literal IP is accepted. An unknown origin is untrusted rather than
     * waved through, because the backend decides LAN membership from this value.
     */
    public static function isValidClient($client): bool
    {
        return is_string($client) && filter_var($client, FILTER_VALIDATE_IP) !== false;
    }

    /**
     * configd splits parameters on whitespace and JSON-RPC bodies are full of it,
     * so the body travels base64 encoded. PHP's encoder emits a single line.
     */
    public static function encodeBody(string $body): string
    {
        return base64_encode($body);
    }

    public static function fault(int $code, string $message): string
    {
        return (string)json_encode([
            'jsonrpc' => '2.0',
            'id' => null,
            'error' => ['code' => $code, 'message' => $message],
        ]);
    }

    /**
     * Classify the backend's reply without reproducing it.
     *
     * The raw JSON is passed straight back on success. Decoding and re-encoding
     * would destroy empty objects: PHP cannot tell {} from [], so every
     * "properties": {} in the tool schemas became "properties": [], which MCP
     * clients reject. Decoding here is only ever used to classify.
     *
     * @return array{kind:string, body:string, status:int}
     */
    public static function interpret(string $raw): array
    {
        $decoded = json_decode($raw, true);
        if (!is_array($decoded)) {
            return [
                'kind' => self::KIND_FAULT,
                'body' => self::fault(-32603, 'WAN quota MCP backend unavailable'),
                'status' => 200,
            ];
        }
        if (!empty($decoded['_notification'])) {
            // A JSON-RPC notification has no response body.
            return ['kind' => self::KIND_NOTIFICATION, 'body' => '', 'status' => 202];
        }
        return ['kind' => self::KIND_JSON, 'body' => $raw, 'status' => 200];
    }
}
