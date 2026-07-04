document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('video');
    const captureBtn = document.getElementById('capture-btn');
    const canvas = document.createElement('canvas');
    const faceDataInput = document.getElementById('face_data');
    const statusText = document.getElementById('camera-status');
    
    if (video) {
        navigator.mediaDevices.getUserMedia({ video: true })
            .then(stream => {
                video.srcObject = stream;
                statusText.innerText = "Camera Active. Please ensure your face is clearly visible.";
                statusText.style.color = "var(--success)";
                if (captureBtn) captureBtn.disabled = false;
            })
            .catch(err => {
                console.error("Camera error:", err);
                statusText.innerText = "Error accessing camera. Please allow camera permissions.";
                statusText.style.color = "var(--danger)";
                captureBtn.disabled = true;
            });
            
        captureBtn.addEventListener('click', (e) => {
            if(!video.srcObject) return;
            e.preventDefault(); // Prevent form submit initially
            
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext('2d').drawImage(video, 0, 0);
            
            const dataUrl = canvas.toDataURL('image/jpeg');
            faceDataInput.value = dataUrl;
            
            // Now submit form
            captureBtn.closest('form').submit();
        });
    }
});
