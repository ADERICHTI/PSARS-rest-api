const { onDocumentUpdated, onDocumentCreated } = require("firebase-functions/v2/firestore");
const { initializeApp } = require("firebase-admin/app");
const { getFirestore } = require("firebase-admin/firestore");

initializeApp();
const db = getFirestore();

// Whenever a user's own fcm_token changes, push the new value out to every
// emergency_contacts record (across all devices) that references this user,
// so the denormalized copy never goes stale.
exports.syncFcmTokenToContacts = onDocumentUpdated("users/{userId}", async (event) => {
  const before = event.data.before.data();
  const after = event.data.after.data();

  if (before.fcm_token === after.fcm_token) return;

  const userId = event.params.userId;
  const newToken = after.fcm_token || null;

  const contactsSnap = await db
    .collectionGroup("emergency_contacts")
    .where("user_id", "==", userId)
    .get();

  if (contactsSnap.empty) return;

  const batch = db.batch();
  contactsSnap.forEach((doc) => batch.update(doc.ref, { fcm_token: newToken }));
  await batch.commit();
});

// Whenever a new user signs up, check if their phone number matches an
// existing SMS-only emergency contact somewhere. If it does, upgrade that
// contact record with the new user's id + fcm_token so they start receiving
// push alerts too, with no action needed from whoever added them.
exports.backfillContactOnSignup = onDocumentCreated("users/{userId}", async (event) => {
  const newUser = event.data.data();
  const phoneNumber = newUser.phone_number;
  if (!phoneNumber) return;

  const userId = event.params.userId;

  const contactsSnap = await db
    .collectionGroup("emergency_contacts")
    .where("phone_number", "==", phoneNumber)
    .get();

  if (contactsSnap.empty) return;

  const batch = db.batch();
  contactsSnap.forEach((doc) => {
    batch.update(doc.ref, {
      user_id: userId,
      fcm_token: newUser.fcm_token || null,
    });
  });
  await batch.commit();
});
