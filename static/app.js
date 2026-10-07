let timeInSeconds = 300;
const countdownElement = document.getElementById('countdown');

const timerInterval = setInterval(() => {
  const minutes = Math.floor(timeInSeconds / 60);
  const seconds = timeInSeconds % 60;
  countdownElement.textContent = 
    `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  
  if (timeInSeconds <= 0) {
    clearInterval(timerInterval);
    countdownElement.textContent = "DEPARTED";
  }
  timeInSeconds--;
}, 1000);

document.getElementById('nlp-submit').addEventListener('click', async () => {
  const prompt = document.getElementById('nlp-input').value;
  if (!prompt) return;

  const response = await fetch('/api/parse-ride', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: prompt })
  });

  if (!response.ok) {
    const error = await response.json();
    alert(`Unable to parse request: ${error.detail || response.statusText}`);
    return;
  }

  const parsed = await response.json();
  const matchResponse = await fetch('/api/ride-requests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: parsed.origin,
      destination: parsed.destination,
      passenger_count: parsed.passenger_count,
      departure_in_minutes: parsed.departure_in_minutes
    })
  });

  if (!matchResponse.ok) {
    const error = await matchResponse.json();
    alert(`Unable to find a match: ${error.detail || matchResponse.statusText}`);
    return;
  }

  const match = await matchResponse.json();
  const matchStatus = match.status === 'queued'
    ? `Queued (${match.frontier_size} requests waiting)`
    : `Matched with ${match.passengers} riders in ${match.group_id}`;
  alert(`Request:\nDestination: ${parsed.destination}\nRiders: ${parsed.passenger_count}\nDeparture: ${parsed.departure_in_minutes} mins\n${matchStatus}`);
});

const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const socket = new WebSocket(`${wsProtocol}//${window.location.host}/ws/cursors`);
const cursorLayer = document.getElementById('cursor-layer');
const clientId = Math.random().toString(36).substring(7);

document.addEventListener('mousemove', (e) => {
  if (socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({
      id: clientId,
      x: e.clientX,
      y: e.clientY
    }));
  }
});

socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  let cursor = document.getElementById(`cursor-${data.id}`);
  
  if (!cursor) {
    cursor = document.createElement('div');
    cursor.id = `cursor-${data.id}`;
    cursor.className = 'ghost-cursor';
    cursorLayer.appendChild(cursor);
  }
  
  cursor.style.transform = `translate(${data.x}px, ${data.y}px)`;
};