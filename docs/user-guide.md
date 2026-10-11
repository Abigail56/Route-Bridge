# RouteBridge Logistics: user guide

Plain-language steps for everyone who uses RouteBridge. Pick your part:

1. [The owner (company)](#1-the-owner)
2. [A shop (merchant)](#2-a-shop-merchant)
3. [The rider](#3-the-rider)
4. [Dispatchers, finance and other staff](#4-dispatchers-finance-and-other-staff)
5. [The platform administrator](#5-the-platform-administrator)
6. [When something goes wrong](#6-when-something-goes-wrong)

---

## 1. The owner

You run the company. Only you can add or remove shops.

### First day
1. Sign in. The **Overview** shows a getting-started card: add a shop, add zones, add riders.
2. **Settings → Zones & rate cards**: add the areas you deliver to and what each costs.
3. **Drivers**: add your riders. Give each rider their access link or QR code so they can open the rider app.
4. **Settings → Members & roles**: add your team (see below).
5. **Settings → Dispatching**: turn on automatic assignment if you want the nearest free rider chosen for you.

### Adding a team member
1. Ask the person to open the site and **sign up**. Before the form, they choose what they will do (shop, dispatcher, operations manager, finance or admin).
2. After signing in they see a screen with their **ID**. They press **Copy a message to send** and send it to you on WhatsApp or SMS.
3. In **Settings → Members & roles** paste the ID, choose their role, and press **Add member**.

No ID, no access. Nobody can be added any other way.

### Adding a shop
1. The shop owner signs up and sends you their **Shop sign-up ID**, the same way.
2. **Settings → Merchants**: type the shop's name, paste the ID, press **Add merchant**.
3. The shop signs in and **registers itself** (phone, address, bank account). Until it does, it cannot create orders.
4. You see its details in **Settings → Merchants → Shop details**, with its own **Shop ID** and a Copy button. Bank details are shown only to you, admins and finance.

### Removing and restoring a shop
- **Remove** (in the shop's card): its login stops working and no new orders can be created. Past orders and statements stay. A shop with deliveries still on the way cannot be removed.
- **Restore** (under **Removed shops**): brings the shop back with its history and its login.

### Every day
- **Overview**: what needs attention right now. The bell lists problems and riders waiting for a delivery code.
- **Dispatch board**: assign riders. When a rider reaches a customer and asks for a code, a card appears at the top (see "Delivery codes" below).
- **Reconciliation**: match cash collected to what was due, and answer shops' claims.
- Everything updates by itself. You never need to refresh.

### Delivery codes (your fraud protection)
A delivery is only completed when the rider enters the code the customer gives them at the door, and the server confirms it. A photo alone is not enough.
1. The rider taps **Text the customer a delivery code**.
2. A card appears on your dashboard with the code and ready-made buttons: **WhatsApp**, **Text message**, **Call**, **Copy message**.
3. Send the code to the customer, then press **Mark as sent**.
4. The customer reads the code to the rider. The rider types it in. The order shows **✓ Verified**.

Codes last 30 minutes. After 5 wrong tries a code locks and a new one must be requested.
If a customer cannot give a code, the rider marks the delivery as failed, and you reschedule it.

---

## 2. A shop (merchant)

1. **Sign up** at the site. Choose "I run a shop" and, if you like, type your shop's name.
2. Send the owner the **Shop sign-up ID** shown after you sign in (press **Copy a message to send**).
3. When the owner has added you, sign in again. You land in **your shop's portal**.
4. **Finish registering your shop** on the Overview: phone, address riders collect from, and the bank account you are paid into (10 digits). You can edit this later.
5. Press **+ New order** for each parcel: customer name and phone, delivery address, amount to collect.
6. Watch it on **My orders**. The list updates by itself and shows a small alert whenever an order is given to a rider, accepted, on the way, at the door or delivered.
7. Open an order for its tracking link (send it to your customer) and to see **✓ Verified** once the customer's code was checked.
8. **Statements** shows cash collected, delivery fees and what is left to pay you. **Problems** is where you report damaged or lost goods, refunds and disputes.

Your **Shop ID** is shown on your Overview with a Copy button. Quote it if you ever need to contact the company.

---

## 3. The rider

1. Open the link or scan the QR code the dispatcher gave you. Add it to your home screen for one-tap access. It works with a weak connection and sends everything once you are back online.
2. **Jobs** lists your orders. Tap one to open it.
3. The **Collect from** card shows the shop to collect from: name, who to ask for, address and a tap-to-call phone number.
4. Use **Navigate** (or Waze) to drive to the address. Mark each step as you go: accepted, on the way, arrived.
5. At the customer's door mark the job as **arrived**. Now **Call customer** works.
6. Press **Text the customer a delivery code**. Ask the customer for the code they received.
7. Enter the code in **Customer's 6-digit code (required)**, add the name of who received it and a photo if you can, collect cash if due, and press **Confirm delivered**.
8. If the customer cannot give a code or nobody is home, choose a reason and mark the delivery **failed**. Do not guess codes: after 5 wrong tries it locks.

---

## 4. Dispatchers, finance and other staff

| Role | What you do |
|---|---|
| Dispatcher | Create orders, assign riders, pass delivery codes to customers |
| Operations manager | Everything a dispatcher does, plus problems, claims and the audit history |
| Finance | Reconciliation, statements, claims decisions, billing, shops' bank details |
| Admin | Members, zones, billing and dispatch settings |

Sign up, send your ID to the owner (see "Adding a team member"), and use the console once added.

---

## 5. The platform administrator

You run RouteBridge itself, not a company's deliveries.
- **Platform** lists the companies on RouteBridge.
- You create a company and set its first owner by their user ID. After that the owner runs it.
- Plans are set by platform staff through the API (there is no button for it in the console yet); see `PUT /platform/tenants/{id}/plan`.
- Your admin ID is kept in the database and the `PLATFORM_ADMIN_SUBJECTS` setting.

---

## 6. When something goes wrong

| What you see | What to do |
|---|---|
| "Your account is not linked to a workspace yet" | Send your ID (shown on that screen) to the company owner |
| A shop cannot create an order and is told to finish registering | Open the Overview and complete the registration form |
| A rider cannot finish a delivery | The customer's code is required. Ask them for it, or mark the delivery failed |
| A code is locked | Ask for a new code ("Text the customer a delivery code") |
| A shop does not appear when adding it | Check the ID was pasted exactly, with no spaces. The ID must be the shop's own sign-up ID |
| The site says you must wait before signing in | Too many sign-in tries: wait 15 minutes |
| The phone link does not open | The computer running RouteBridge may be off or asleep. Ask whoever runs it to start it (see the README, "Day to day on this computer") |
