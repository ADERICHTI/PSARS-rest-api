importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyCMbR_HP7TTi9tfcSPlIG59PVTkz1bH0AE",
  authDomain: "psars-26.firebaseapp.com",
  projectId: "psars-26",
  storageBucket: "psars-26.firebasestorage.app",
  messagingSenderId: "481486286858",
  appId: "1:481486286858:web:f474d6fe1b89b35eaf6ff3",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title = (payload.notification && payload.notification.title) || "PSARS Alert";
  const body = (payload.notification && payload.notification.body) || "";
  self.registration.showNotification(title, { body });
});
