### Webhooks:

#### Messenger Settings

1. Configure webhooks for messenger:

- Callback URL: https://chambella.harmonia.lat/webhook-messenger
- Verify token: GPSc0ntr0l1
- Webhook fields:
    - ​message_deliveries
    - message_reads
    - messages
    - messaging_optins
    - messaging_postbacks
    - messaging_referrals

2. Generate access tokens
- Page Name: GPScontrol
- Webhook Subscriptions:
    - messages
    - messaging_optins 
    - message_deliveries
    - messaging_referrals
    - messaging_postbacks
    - message_reads


#### Whasapp Settings

1. Configure webhooks for messenger:
    - Callback URL: https://chambella-whats.armaddia.lat/webhook-whatsapp
    - Verify token: GPSc0ntr0l1
    - Webhook fields:
        - messages




### When creating in meta the app:

For an app that sends and receives messages via Messenger and WhatsApp (using Meta APIs), you should select:

"Manage everything on your Page"

This option is required to access Messenger and WhatsApp Business APIs, manage webhooks, send/receive messages, and interact with users via your Facebook Page.

Do not select "Create an app without a use case" unless you want to configure everything manually.
"Manage everything on your Page" is the recommended and supported use case for chatbots and messaging integrations.
