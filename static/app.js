const state = {
  user: null,
  register: false,
  map: null,
  markers: new Map(),
  driverMarkers: new Map(),
  routeLine: null,
  pickup: null,
  dropoff: null,
  currentLocation: null,
  watchId: null,
  lastLocationSentAt: 0,
  pollTimer: null,
  toastTimer: null
};

const byId = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    const error = new Error(result.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function notify(message) {
  const toast = byId('toast');
  toast.textContent = message;
  toast.classList.add('visible');
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => toast.classList.remove('visible'), 3800);
}

function setBusy(button, busy, busyText) {
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = busyText;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
  }
}

function renderAuthMode() {
  byId('auth-title').textContent = state.register ? 'Create your account' : 'Sign in';
  byId('auth-eyebrow').textContent = state.register ? 'Join AutoShare' : 'Welcome back';
  byId('auth-mode').textContent = state.register ? 'I already have an account' : 'Create account';
  byId('auth-submit').textContent = state.register ? 'Create account' : 'Sign in';
  byId('name-field').classList.toggle('hidden', !state.register);
  byId('role-field').classList.toggle('hidden', !state.register);
  byId('password-hint').classList.toggle('hidden', !state.register);
  byId('auth-name').required = state.register;
  byId('auth-password').autocomplete = state.register ? 'new-password' : 'current-password';
  byId('auth-password').minLength = state.register ? 12 : 1;
}

function showAuth() {
  state.user = null;
  stopLocationWatch();
  window.clearInterval(state.pollTimer);
  if (state.map) {
    state.map.remove();
    state.map = null;
  }
  state.markers.clear();
  state.driverMarkers.clear();
  state.pickup = null;
  state.dropoff = null;
  state.currentLocation = null;
  byId('dashboard').classList.add('hidden');
  byId('auth-screen').classList.remove('hidden');
  renderAuthMode();
}

function showDashboard(user) {
  state.user = user;
  byId('auth-screen').classList.add('hidden');
  byId('dashboard').classList.remove('hidden');
  byId('account-label').textContent = `${user.full_name} · ${user.role}`;
  const isDriver = user.role === 'driver';
  byId('rider-panel').classList.toggle('hidden', isDriver);
  byId('driver-panel').classList.toggle('hidden', !isDriver);
  byId('dashboard-eyebrow').textContent = isDriver ? 'Driver workspace' : 'Rider workspace';
  byId('dashboard-title').textContent = isDriver ? 'Welcome to your driver desk' : 'Where are you headed?';
  window.setTimeout(initializeMap, 50);
  if (isDriver) {
    refreshVehicles();
    updateDriverVerification();
    if (user.is_online) startLocationWatch();
    pollDriverRequests();
  } else {
    refreshRides();
    if (state.currentLocation) refreshNearbyDrivers();
  }
  window.clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(() => {
    if (!state.user) return;
    refreshRides();
    if (state.user.role === 'driver' && state.user.is_online) pollDriverRequests();
    if (state.user.role === 'rider' && state.currentLocation) refreshNearbyDrivers();
  }, 8000);
}

function initializeMap() {
  if (!window.L) {
    notify('The map library did not load. Check your connection and refresh.');
    return;
  }
  if (!state.map) {
    const mapId = state.user?.role === 'driver' ? 'driver-map' : 'map';
    state.map = L.map(mapId, { zoomControl: true }).setView([10.18, 76.44], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(state.map);
    if (state.user?.role === 'rider') {
      state.map.on('click', (event) => {
        const point = { latitude: event.latlng.lat, longitude: event.latlng.lng };
        if (byId('map-mode').value === 'pickup') {
          state.pickup = point;
          byId('pickup').value = `Map pickup (${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)})`;
        } else {
          state.dropoff = point;
          byId('dropoff').value = `Map drop-off (${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)})`;
        }
        renderRouteMarkers();
      });
    }
  }
  window.setTimeout(() => state.map.invalidateSize(), 60);
}

function placeMarker(key, point, label, color = '#34d399') {
  if (!state.map || !point) return;
  let marker = state.markers.get(key);
  const icon = L.divIcon({
    className: '',
    html: `<span style="display:block;width:16px;height:16px;border:3px solid #fff;border-radius:50%;background:${color};box-shadow:0 1px 8px #0f172a"></span>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8]
  });
  if (marker) {
    marker.setLatLng([point.latitude, point.longitude]).setIcon(icon);
  } else {
    marker = L.marker([point.latitude, point.longitude], { icon }).addTo(state.map);
    state.markers.set(key, marker);
  }
  marker.bindTooltip(label, { direction: 'top' });
}

function renderRouteMarkers() {
  if (!state.map) return;
  if (state.pickup) placeMarker('pickup', state.pickup, 'Pickup', '#34d399');
  if (state.dropoff) placeMarker('dropoff', state.dropoff, 'Drop-off', '#fb7185');
  if (state.routeLine) state.routeLine.remove();
  const points = [state.pickup, state.dropoff]
    .filter(Boolean)
    .map((point) => [point.latitude, point.longitude]);
  if (points.length === 2) {
    state.routeLine = L.polyline(points, {
      color: '#34d399',
      weight: 4,
      opacity: 0.85,
      dashArray: '8 8'
    }).addTo(state.map);
    state.map.fitBounds(state.routeLine.getBounds().pad(0.3));
  } else if (points.length === 1) {
    state.map.setView(points[0], 14);
  }
}

function locateCurrentUser() {
  if (!navigator.geolocation) {
    notify('Geolocation is unavailable in this browser.');
    return;
  }
  byId('location-status').textContent = 'Getting your location…';
  navigator.geolocation.getCurrentPosition(
    (position) => {
      const point = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude
      };
      state.currentLocation = point;
      if (!state.pickup && state.user?.role === 'rider') {
        state.pickup = point;
        byId('pickup').value = 'My current location';
      }
      if (state.user?.role === 'driver') {
        byId('driver-gps').textContent = `${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)}`;
      }
      byId('location-status').textContent = 'Location updated';
      placeMarker('current', point, 'Your location', '#38bdf8');
      if (state.map) state.map.setView([point.latitude, point.longitude], 14);
      renderRouteMarkers();
      if (state.user?.role === 'rider') refreshNearbyDrivers();
    },
    (error) => {
      byId('location-status').textContent = 'Location not shared';
      notify(error.message || 'Could not access your location.');
    },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 10000 }
  );
}

async function refreshNearbyDrivers() {
  if (!state.currentLocation || state.user?.role !== 'rider') return;
  const params = new URLSearchParams({
    latitude: String(state.currentLocation.latitude),
    longitude: String(state.currentLocation.longitude),
    radius_km: '10',
    passenger_count: byId('passenger-count').value || '1'
  });
  try {
    const drivers = await api(`/api/drivers/nearby?${params}`);
    byId('nearby-count').textContent = `${drivers.length} within 10 km`;
    const list = byId('nearby-list');
    list.replaceChildren();
    if (!drivers.length) {
      list.textContent = 'No recently active verified drivers nearby.';
    }
    const activeIds = new Set(drivers.map((driver) => driver.driver_id));
    for (const [id, marker] of state.driverMarkers) {
      if (!activeIds.has(id)) {
        marker.remove();
        state.driverMarkers.delete(id);
      }
    }
    for (const driver of drivers) {
      const row = document.createElement('div');
      row.className = 'flex items-center justify-between gap-3 rounded-xl bg-slate-950/70 px-3 py-3';
      const details = document.createElement('div');
      const name = document.createElement('p');
      name.className = 'font-semibold text-slate-200';
      name.textContent = driver.full_name;
      const vehicle = document.createElement('p');
      vehicle.className = 'mt-1 text-xs text-slate-400';
      vehicle.textContent = `${driver.vehicle} · ${driver.capacity} seats`;
      details.append(name, vehicle);
      const distance = document.createElement('span');
      distance.className = 'whitespace-nowrap text-xs text-emerald-300';
      distance.textContent = `${driver.distance_km} km`;
      row.append(details, distance);
      list.append(row);
      if (state.map) {
        let marker = state.driverMarkers.get(driver.driver_id);
        const position = [driver.latitude, driver.longitude];
        if (!marker) {
          marker = L.circleMarker(position, {
            radius: 8,
            color: '#052e2b',
            fillColor: '#2dd4bf',
            fillOpacity: 1,
            weight: 2
          }).addTo(state.map);
          state.driverMarkers.set(driver.driver_id, marker);
        } else {
          marker.setLatLng(position);
        }
        const tooltip = document.createElement('span');
        tooltip.textContent = `${driver.full_name} · ${driver.distance_km} km`;
        marker.bindTooltip(tooltip);
      }
    }
  } catch (error) {
    if (error.status !== 401) notify(error.message);
  }
}

async function requestRide() {
  const pickup = byId('pickup').value.trim();
  const dropoff = byId('dropoff').value.trim();
  const passengerCount = Number(byId('passenger-count').value);
  if (!pickup || !dropoff || !Number.isInteger(passengerCount) || passengerCount < 1 || passengerCount > 8) {
    notify('Enter pickup, drop-off, and a passenger count from 1 to 8.');
    return;
  }
  if (!state.pickup) {
    notify('Set a pickup by allowing location access or selecting a point on the map.');
    return;
  }
  try {
    const ride = await api('/api/rides', {
      method: 'POST',
      body: JSON.stringify({
        pickup,
        dropoff,
        passenger_count: passengerCount,
        pickup_latitude: state.pickup.latitude,
        pickup_longitude: state.pickup.longitude,
        ...(state.dropoff ? {
          dropoff_latitude: state.dropoff.latitude,
          dropoff_longitude: state.dropoff.longitude
        } : {})
      })
    });
    notify(`Ride #${ride.id} has been sent to nearby drivers.`);
    await refreshRides();
  } catch (error) {
    notify(error.message);
  }
}

async function parseRide() {
  const query = byId('ride-query').value.trim();
  if (query.length < 3) {
    notify('Describe your pickup, destination, and passenger count.');
    return;
  }
  const button = byId('parse-ride-button');
  setBusy(button, true, 'Parsing…');
  try {
    const intent = await api('/api/parse-ride', {
      method: 'POST',
      body: JSON.stringify({ query })
    });
    byId('pickup').value = intent.pickup;
    byId('dropoff').value = intent.dropoff;
    byId('passenger-count').value = String(intent.passenger_count);
    notify('Ride details parsed. Review pickup and drop-off before requesting.');
  } catch (error) {
    notify(error.message);
  } finally {
    setBusy(button, false);
  }
}

function statusPill(status) {
  const pill = document.createElement('span');
  pill.className = `status-pill ${status}`;
  pill.textContent = status.replaceAll('_', ' ');
  return pill;
}

async function refreshRides() {
  if (!state.user) return;
  try {
    const rides = await api('/api/rides/mine');
    const list = byId('rides-list');
    list.replaceChildren();
    if (!rides.length) {
      list.textContent = 'No rides yet.';
      return;
    }
    for (const ride of rides) {
      const card = document.createElement('article');
      card.className = 'rounded-xl border border-slate-800 bg-slate-950/60 p-3';
      const head = document.createElement('div');
      head.className = 'flex items-center justify-between gap-2';
      const title = document.createElement('p');
      title.className = 'font-semibold text-slate-100';
      title.textContent = `Ride #${ride.id}`;
      head.append(title, statusPill(ride.status));
      const route = document.createElement('p');
      route.className = 'mt-2 text-slate-300';
      route.textContent = `${ride.pickup} → ${ride.dropoff}`;
      const meta = document.createElement('p');
      meta.className = 'mt-1 text-xs text-slate-500';
      meta.textContent = `${ride.passenger_count} passenger(s) · Estimated fare ${Number(ride.fare_amount).toFixed(2)}`;
      card.append(head, route, meta);
      if (state.user.role === 'driver' && ride.driver_id === state.user.id) {
        if (ride.status === 'accepted') {
          card.append(actionButton('Start ride', () => updateRideStatus(ride.id, 'in_transit')));
        } else if (ride.status === 'in_transit') {
          card.append(actionButton('Complete ride', () => updateRideStatus(ride.id, 'completed')));
        }
      }
      list.append(card);
      if (state.user.role === 'rider') {
        if (['accepted', 'in_transit'].includes(ride.status)) {
          refreshRideDriverLocation(ride.id);
        } else {
          const oldMarker = state.markers.get(`ride-driver-${ride.id}`);
          if (oldMarker) {
            oldMarker.remove();
            state.markers.delete(`ride-driver-${ride.id}`);
          }
        }
      }
    }
  } catch (error) {
    if (error.status !== 401) notify(error.message);
  }
}

async function refreshRideDriverLocation(rideId) {
  try {
    const location = await api(`/api/rides/${rideId}/driver-location`);
    if (!state.map || state.user?.role !== 'rider') return;
    const key = `ride-driver-${rideId}`;
    let marker = state.markers.get(key);
    const position = [location.latitude, location.longitude];
    if (!marker) {
      marker = L.circleMarker(position, {
        radius: 10,
        color: '#fff',
        fillColor: '#38bdf8',
        fillOpacity: 1,
        weight: 3
      }).addTo(state.map);
      state.markers.set(key, marker);
    } else {
      marker.setLatLng(position);
    }
    const tooltip = document.createElement('span');
    tooltip.textContent = `Your driver · ride #${rideId}`;
    marker.bindTooltip(tooltip);
  } catch (error) {
    if (error.status !== 404 && error.status !== 409 && error.status !== 401) {
      notify(error.message);
    }
  }
}

function actionButton(label, action) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'secondary-button mt-3 !min-h-9 !px-3 !py-2';
  button.textContent = label;
  button.addEventListener('click', action);
  return button;
}

async function updateRideStatus(rideId, status) {
  try {
    await api(`/api/rides/${rideId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status })
    });
    notify(`Ride status updated to ${status.replaceAll('_', ' ')}.`);
    await refreshRides();
  } catch (error) {
    notify(error.message);
  }
}

async function refreshVehicles() {
  try {
    const vehicles = await api('/api/drivers/me/vehicles');
    const list = byId('vehicle-list');
    list.replaceChildren();
    if (!vehicles.length) {
      list.textContent = 'No vehicles submitted yet.';
      list.className = 'mt-4 text-sm text-slate-400';
      updateDriverVerification();
      return;
    }
    list.className = 'mt-4 space-y-2';
    for (const vehicle of vehicles) {
      const row = document.createElement('div');
      row.className = 'flex items-center justify-between rounded-xl bg-slate-950/70 px-3 py-3';
      const info = document.createElement('p');
      info.className = 'text-sm font-medium text-slate-200';
      info.textContent = `${vehicle.license_plate} · ${vehicle.make_model} · ${vehicle.capacity} seats`;
      row.append(info, statusPill(vehicle.verification_status));
      list.append(row);
    }
    const freshUser = await api('/api/me');
    state.user = freshUser;
    updateDriverVerification();
  } catch (error) {
    if (error.status !== 401) notify(error.message);
  }
}

function updateDriverVerification() {
  const verified = state.user?.is_verified;
  byId('driver-verification').textContent = verified
    ? 'Account verified. Add a verified vehicle to go online.'
    : 'Driver verification is pending. An administrator must verify your account and vehicle.';
  byId('online-toggle').textContent = state.user?.is_online ? 'Go offline' : 'Go online';
  byId('online-toggle').classList.toggle('bg-rose-900/60', Boolean(state.user?.is_online));
}

async function submitVehicle(event) {
  event.preventDefault();
  try {
    await api('/api/drivers/me/vehicles', {
      method: 'POST',
      body: JSON.stringify({
        license_plate: byId('vehicle-plate').value,
        make_model: byId('vehicle-model').value,
        capacity: Number(byId('vehicle-capacity').value)
      })
    });
    byId('vehicle-form').reset();
    byId('vehicle-capacity').value = '4';
    notify('Vehicle submitted. It must be verified before dispatch.');
    await refreshVehicles();
  } catch (error) {
    notify(error.message);
  }
}

async function toggleOnline() {
  const desired = !state.user.is_online;
  try {
    const result = await api('/api/drivers/me/status', {
      method: 'PUT',
      body: JSON.stringify({ is_online: desired })
    });
    state.user.is_online = result.is_online;
    updateDriverVerification();
    if (result.is_online) {
      startLocationWatch();
      notify('You are online and visible to nearby riders.');
      pollDriverRequests();
    } else {
      stopLocationWatch();
      byId('dispatch-list').textContent = 'Go online to receive nearby requests.';
      byId('dispatch-count').textContent = 'Polling paused';
      notify('You are offline.');
    }
  } catch (error) {
    notify(error.message);
  }
}

function startLocationWatch() {
  if (!navigator.geolocation || state.watchId !== null) return;
  byId('driver-gps').textContent = 'Waiting for device GPS…';
  state.watchId = navigator.geolocation.watchPosition(
    async (position) => {
      const isFirstLocation = state.currentLocation === null;
      const point = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude
      };
      state.currentLocation = point;
      byId('driver-gps').textContent = `${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)}`;
      byId('location-status').textContent = 'Sharing driver location';
      placeMarker('current', point, 'Your live driver location', '#38bdf8');
      if (state.map && isFirstLocation) state.map.setView([point.latitude, point.longitude], 14);
      if (Date.now() - state.lastLocationSentAt < 5000) return;
      state.lastLocationSentAt = Date.now();
      try {
        await api('/api/drivers/me/location', {
          method: 'PUT',
          body: JSON.stringify(point)
        });
      } catch (error) {
        if (error.status !== 401) notify(error.message);
      }
    },
    (error) => {
      byId('driver-gps').textContent = error.message || 'GPS permission is required to go online.';
    },
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
  );
}

function stopLocationWatch() {
  if (state.watchId !== null && navigator.geolocation) {
    navigator.geolocation.clearWatch(state.watchId);
  }
  state.watchId = null;
}

async function pollDriverRequests() {
  if (state.user?.role !== 'driver' || !state.user.is_online) return;
  try {
    const requests = await api('/api/driver/rides/requests');
    byId('dispatch-count').textContent = `${requests.length} request(s)`;
    renderDispatchRequests(requests);
  } catch (error) {
    if (error.status !== 401) notify(error.message);
  }
}

function renderDispatchRequests(requests) {
  const list = byId('dispatch-list');
  list.replaceChildren();
  if (!requests.length) {
    list.textContent = 'No nearby requests right now. New requests refresh automatically.';
    return;
  }
  for (const ride of requests) {
    const card = document.createElement('article');
    card.className = 'rounded-xl border border-emerald-900/70 bg-slate-950/70 p-4';
    const heading = document.createElement('p');
    heading.className = 'font-bold text-slate-100';
    heading.textContent = `Ride #${ride.id} · ${ride.passenger_count} passenger(s)`;
    const route = document.createElement('p');
    route.className = 'mt-2 text-slate-300';
    route.textContent = `${ride.pickup} → ${ride.dropoff}`;
    const fare = document.createElement('p');
    fare.className = 'mt-1 text-xs text-slate-400';
    fare.textContent = `Estimated fare ${Number(ride.fare_amount).toFixed(2)}`;
    const actions = document.createElement('div');
    actions.className = 'mt-3 flex gap-2';
    actions.append(
      actionButton('Accept ride', () => decideRide(ride.id, true)),
      actionButton('Decline', () => decideRide(ride.id, false))
    );
    card.append(heading, route, fare, actions);
    list.append(card);
  }
}

async function decideRide(rideId, accept) {
  try {
    await api(`/api/driver/rides/${rideId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ accept })
    });
    notify(accept ? 'Ride accepted.' : 'Request declined.');
    if (accept) {
      await api('/api/me').then((user) => {
        state.user = user;
        updateDriverVerification();
      });
    }
    await Promise.all([refreshRides(), pollDriverRequests()]);
  } catch (error) {
    notify(error.message);
    await pollDriverRequests();
  }
}

byId('auth-mode').addEventListener('click', () => {
  state.register = !state.register;
  renderAuthMode();
});

byId('auth-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = byId('auth-submit');
  setBusy(button, true, state.register ? 'Creating…' : 'Signing in…');
  try {
    const endpoint = state.register ? '/api/auth/register' : '/api/auth/login';
    const payload = {
      email: byId('auth-email').value,
      password: byId('auth-password').value
    };
    if (state.register) {
      payload.full_name = byId('auth-name').value;
      payload.role = byId('auth-role').value;
    }
    const result = await api(endpoint, { method: 'POST', body: JSON.stringify(payload) });
    showDashboard(result.user);
  } catch (error) {
    notify(error.message);
  } finally {
    setBusy(button, false);
  }
});

byId('logout-button').addEventListener('click', async () => {
  try {
    await api('/api/auth/logout', { method: 'POST' });
  } finally {
    showAuth();
  }
});
byId('locate-button').addEventListener('click', locateCurrentUser);
byId('parse-ride-button').addEventListener('click', parseRide);
byId('request-ride-button').addEventListener('click', requestRide);
byId('vehicle-form').addEventListener('submit', submitVehicle);
byId('online-toggle').addEventListener('click', toggleOnline);
byId('passenger-count').addEventListener('change', refreshNearbyDrivers);

api('/api/me')
  .then(showDashboard)
  .catch((error) => {
    if (error.status !== 401) notify(error.message);
    showAuth();
  });
