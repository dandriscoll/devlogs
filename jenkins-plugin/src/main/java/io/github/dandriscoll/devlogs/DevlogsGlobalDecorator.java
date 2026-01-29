package io.github.dandriscoll.devlogs;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import okhttp3.*;
import org.jenkinsci.plugins.workflow.log.TaskListenerDecorator;

import javax.annotation.Nonnull;
import java.io.IOException;
import java.io.OutputStream;
import java.io.Serializable;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Global TaskListenerDecorator that captures all pipeline console output.
 * This is applied via the Factory extension when a DevlogsAction is present on the build.
 */
public final class DevlogsGlobalDecorator extends TaskListenerDecorator implements Serializable {
    private static final long serialVersionUID = 1L;
    private static final Logger LOGGER = Logger.getLogger(DevlogsGlobalDecorator.class.getName());
    private static final String DEBUG_PREFIX = "[DEVLOGS-DEBUG] ";

    private final String url;
    private final String index;
    private final String runId;
    private final String jobName;
    private final int buildNumber;
    private final String buildUrl;
    private final String application;
    private final String component;
    private final String environment;
    private final String version;
    private final boolean pipeline;
    private final AtomicInteger seq;

    public DevlogsGlobalDecorator(DevlogsAction action) {
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsGlobalDecorator constructor called for build " + action.getBuildNumber());
        this.url = action.getUrl();
        this.index = action.getIndex();
        this.runId = action.getRunId();
        this.jobName = action.getJobName();
        this.buildNumber = action.getBuildNumber();
        this.buildUrl = action.getBuildUrl();
        this.application = action.getApplication();
        this.component = action.getComponent();
        this.environment = action.getEnvironment();
        this.version = action.getVersion();
        this.pipeline = action.isPipeline();
        this.seq = new AtomicInteger(0);
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsGlobalDecorator created: index=" + index + ", pipeline=" + pipeline);
    }

    @Nonnull
    @Override
    public OutputStream decorate(@Nonnull OutputStream logger) throws IOException, InterruptedException {
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "decorate() called for build " + buildNumber +
            ", logger class: " + logger.getClass().getName());
        DevlogsOutputStream stream = new DevlogsOutputStream(logger, url, index, runId, jobName, buildNumber, buildUrl, seq,
            application, component, environment, version, pipeline);
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "decorate() returning DevlogsOutputStream instance " + System.identityHashCode(stream));
        return stream;
    }

    // Factory removed - we use withContext() in DevlogsStep instead.
    // The Factory was creating duplicate decorators, causing each log line
    // to be sent twice and with conflicting seq numbers.

    /**
     * OutputStream that captures log lines and sends them to devlogs.
     */
    private static class DevlogsOutputStream extends OutputStream implements Serializable {
        private static final long serialVersionUID = 2L;
        private static final int BUFFER_SIZE = 8192;
        private static final int BATCH_SIZE = 1;  // Send immediately - streams may not be closed properly
        private static final long BATCH_TIMEOUT_MS = 1000; // 1 second

        private final OutputStream delegate;
        private final String baseUrl;
        private final String index;
        private final String runId;
        private final String jobName;
        private final int buildNumber;
        private final String buildUrl;
        private final AtomicInteger seq;
        private final String application;
        private final String component;
        private final String environment;
        private final String version;
        private final boolean pipeline;
        private final int instanceId;

        private final byte[] buffer = new byte[BUFFER_SIZE];
        private int bufferPos = 0;
        private final StringBuilder lineBuffer = new StringBuilder();
        private final StringBuilder batchBuffer = new StringBuilder();
        private final JsonArray collectorBatch = new JsonArray();
        private int batchCount = 0;
        private long lastBatchTime = System.currentTimeMillis();
        private String currentLineTimestamp = null;
        private final String authHeader;
        private boolean errorReported = false;

        // Debug counters
        private final AtomicLong totalBytesWritten = new AtomicLong(0);
        private final AtomicLong totalLinesProcessed = new AtomicLong(0);
        private final AtomicLong totalBatchesSent = new AtomicLong(0);

        private transient OkHttpClient client;
        private transient Gson gson;

        private static final DateTimeFormatter ISO_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC);

        private static final AtomicInteger INSTANCE_COUNTER = new AtomicInteger(0);

        public DevlogsOutputStream(OutputStream delegate, String url, String index, String runId,
                                   String jobName, int buildNumber, String buildUrl, AtomicInteger seq,
                                   String application, String component, String environment,
                                   String version, boolean pipeline) {
            this.instanceId = INSTANCE_COUNTER.incrementAndGet();
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId + " constructor called for build " + buildNumber);
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId + " delegate class: " + delegate.getClass().getName());

            this.delegate = delegate;
            this.index = index;
            this.runId = runId;
            this.jobName = jobName;
            this.buildNumber = buildNumber;
            this.buildUrl = buildUrl;
            this.seq = seq;
            this.application = application;
            this.component = component;
            this.environment = environment;
            this.version = version;
            this.pipeline = pipeline;

            // Parse URL to extract credentials and base URL
            String parsedBaseUrl = url;
            String parsedAuthHeader = null;

            try {
                URI uri = new URI(url);
                String userInfo = uri.getUserInfo();
                if (userInfo != null && !userInfo.isEmpty()) {
                    int port = uri.getPort();
                    String portStr = (port > 0) ? ":" + port : "";
                    String path = uri.getPath();

                    if (pipeline) {
                        parsedAuthHeader = "Bearer " + userInfo;
                        parsedBaseUrl = uri.getScheme() + "://" + uri.getHost() + portStr + (path != null ? path : "");
                    } else {
                        parsedAuthHeader = "Basic " + Base64.getEncoder().encodeToString(
                            userInfo.getBytes(StandardCharsets.UTF_8));
                        if (path != null && path.lastIndexOf('/') > 0) {
                            path = path.substring(0, path.lastIndexOf('/'));
                        } else {
                            path = "";
                        }
                        parsedBaseUrl = uri.getScheme() + "://" + uri.getHost() + portStr + path;
                    }
                } else {
                    if (!pipeline) {
                        int lastSlash = url.lastIndexOf('/');
                        if (lastSlash > 0) {
                            parsedBaseUrl = url.substring(0, lastSlash);
                        }
                    }
                }
            } catch (URISyntaxException e) {
                LOGGER.log(Level.WARNING, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId + " URL parse error: " + e.getMessage());
                if (!pipeline) {
                    int lastSlash = url.lastIndexOf('/');
                    if (lastSlash > 0) {
                        parsedBaseUrl = url.substring(0, lastSlash);
                    }
                }
            }

            this.baseUrl = parsedBaseUrl;
            this.authHeader = parsedAuthHeader;
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId + " baseUrl: " + parsedBaseUrl);
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId + " authHeader present: " + (parsedAuthHeader != null));
            initTransients();
        }

        private void initTransients() {
            if (client == null) {
                client = new OkHttpClient.Builder()
                    .followRedirects(true)
                    .followSslRedirects(true)
                    .build();
            }
            if (gson == null) {
                gson = new Gson();
            }
        }

        @Override
        public void write(int b) throws IOException {
            delegate.write(b);
            totalBytesWritten.incrementAndGet();
            buffer[bufferPos++] = (byte) b;
            if (b == '\n' || bufferPos >= BUFFER_SIZE) {
                processBuffer();
            }
        }

        @Override
        public void write(byte[] b, int off, int len) throws IOException {
            delegate.write(b, off, len);
            totalBytesWritten.addAndGet(len);
            for (int i = 0; i < len; i++) {
                buffer[bufferPos++] = b[off + i];
                if (b[off + i] == '\n' || bufferPos >= BUFFER_SIZE) {
                    processBuffer();
                }
            }
        }

        @Override
        public void flush() throws IOException {
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId + " flush() called, " +
                "totalBytes=" + totalBytesWritten.get() + ", totalLines=" + totalLinesProcessed.get() +
                ", batchCount=" + batchCount);
            delegate.flush();
            if (bufferPos > 0) {
                processBuffer();
            }
            if (lineBuffer.length() > 0) {
                String timestamp = (currentLineTimestamp != null) ? currentLineTimestamp : formatTimestamp();
                sendLine(lineBuffer.toString(), timestamp);
                lineBuffer.setLength(0);
                currentLineTimestamp = null;
            }
            flushBatch();
        }

        @Override
        public void close() throws IOException {
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId + " close() called, " +
                "totalBytes=" + totalBytesWritten.get() + ", totalLines=" + totalLinesProcessed.get() +
                ", totalBatches=" + totalBatchesSent.get());
            flush();
            delegate.close();
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId + " closed successfully");
        }

        private void processBuffer() {
            if (bufferPos == 0) return;
            String text = new String(buffer, 0, bufferPos, StandardCharsets.UTF_8);
            bufferPos = 0;

            for (char c : text.toCharArray()) {
                if (c == '\n') {
                    if (lineBuffer.length() > 0) {
                        String timestamp = (currentLineTimestamp != null) ? currentLineTimestamp : formatTimestamp();
                        sendLine(lineBuffer.toString(), timestamp);
                        lineBuffer.setLength(0);
                        currentLineTimestamp = null;
                    }
                } else {
                    if (lineBuffer.length() == 0 && currentLineTimestamp == null) {
                        currentLineTimestamp = formatTimestamp();
                    }
                    lineBuffer.append(c);
                }
            }
        }

        private String formatTimestamp() {
            return ISO_FORMATTER.format(Instant.now());
        }

        private void sendLine(String line, String timestamp) {
            if (line.trim().isEmpty()) return;

            totalLinesProcessed.incrementAndGet();
            long lineNum = totalLinesProcessed.get();

            // Log first 5 lines and every 10th line after that
            if (lineNum <= 5 || lineNum % 10 == 0) {
                String preview = line.length() > 50 ? line.substring(0, 50) + "..." : line;
                LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                    " sendLine() line #" + lineNum + ": " + preview);
            }

            try {
                initTransients();

                long currentTime = System.currentTimeMillis();
                if (batchCount > 0 && (currentTime - lastBatchTime) >= BATCH_TIMEOUT_MS) {
                    LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                        " batch timeout triggered, flushing " + batchCount + " items");
                    flushBatch();
                }

                if (pipeline) {
                    JsonObject doc = new JsonObject();
                    doc.addProperty("application", application);
                    doc.addProperty("component", component);
                    doc.addProperty("timestamp", timestamp);
                    doc.addProperty("message", line);
                    doc.addProperty("level", "info");
                    doc.addProperty("area", jobName);

                    if (environment != null && !environment.isEmpty()) {
                        doc.addProperty("environment", environment);
                    }
                    if (version != null && !version.isEmpty()) {
                        doc.addProperty("version", version);
                    }

                    JsonObject fields = new JsonObject();
                    fields.addProperty("run_id", runId);
                    fields.addProperty("job", jobName);
                    fields.addProperty("build_number", buildNumber);
                    fields.addProperty("build_url", buildUrl);
                    fields.addProperty("seq", seq.incrementAndGet());
                    doc.add("fields", fields);

                    collectorBatch.add(doc);
                } else {
                    JsonObject doc = new JsonObject();
                    doc.addProperty("doc_type", "log_entry");
                    doc.addProperty("application", application);
                    doc.addProperty("component", component);
                    doc.addProperty("timestamp", timestamp);
                    doc.addProperty("message", line);
                    doc.addProperty("level", "info");
                    doc.addProperty("area", jobName);

                    if (environment != null && !environment.isEmpty()) {
                        doc.addProperty("environment", environment);
                    }
                    if (version != null && !version.isEmpty()) {
                        doc.addProperty("version", version);
                    }

                    JsonObject fields = new JsonObject();
                    fields.addProperty("run_id", runId);
                    fields.addProperty("job", jobName);
                    fields.addProperty("build_number", buildNumber);
                    fields.addProperty("build_url", buildUrl);
                    fields.addProperty("seq", seq.incrementAndGet());
                    doc.add("fields", fields);

                    doc.addProperty("logger", "jenkins");
                    doc.addProperty("process", buildNumber);
                    doc.addProperty("thread", seq.get());

                    batchBuffer.append("{\"index\":{\"_index\":\"").append(index).append("\"}}\n");
                    batchBuffer.append(gson.toJson(doc)).append("\n");
                }

                batchCount++;
                if (batchCount == 1) {
                    lastBatchTime = currentTime;
                }
                if (batchCount >= BATCH_SIZE) {
                    LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                        " batch size reached, flushing " + batchCount + " items");
                    flushBatch();
                }
            } catch (Exception e) {
                LOGGER.log(Level.WARNING, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                    " sendLine() exception: " + e.getMessage(), e);
            }
        }

        private void flushBatch() {
            if (batchCount == 0) return;

            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                " flushBatch() called with " + batchCount + " items");
            totalBatchesSent.incrementAndGet();

            try {
                initTransients();

                Request request;
                String targetUrl;

                if (pipeline) {
                    targetUrl = baseUrl.endsWith("/") ? baseUrl + "v1/logs" : baseUrl + "/v1/logs";

                    JsonObject payload = new JsonObject();
                    payload.add("records", collectorBatch);

                    RequestBody body = RequestBody.create(
                        gson.toJson(payload),
                        MediaType.parse("application/json")
                    );

                    Request.Builder requestBuilder = new Request.Builder()
                        .url(targetUrl)
                        .post(body);

                    if (authHeader != null) {
                        requestBuilder.addHeader("Authorization", authHeader);
                    }

                    request = requestBuilder.build();

                    while (collectorBatch.size() > 0) {
                        collectorBatch.remove(0);
                    }
                } else {
                    targetUrl = baseUrl + "/_bulk";

                    RequestBody body = RequestBody.create(
                        batchBuffer.toString(),
                        MediaType.parse("application/x-ndjson")
                    );

                    Request.Builder requestBuilder = new Request.Builder()
                        .url(targetUrl)
                        .post(body);

                    if (authHeader != null) {
                        requestBuilder.addHeader("Authorization", authHeader);
                    }

                    request = requestBuilder.build();
                }

                LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                    " sending batch to " + targetUrl);

                try (Response response = client.newCall(request).execute()) {
                    if (response.isSuccessful()) {
                        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                            " batch sent successfully, HTTP " + response.code());
                    } else {
                        String responseBody = response.body() != null ? response.body().string() : "";
                        String preview = responseBody.length() > 200 ? responseBody.substring(0, 200) + "..." : responseBody;
                        LOGGER.log(Level.WARNING, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                            " batch send failed, HTTP " + response.code() + ": " + preview);
                        errorReported = true;
                    }
                }

                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            } catch (Exception e) {
                LOGGER.log(Level.WARNING, DEBUG_PREFIX + "DevlogsOutputStream #" + instanceId +
                    " flushBatch() exception: " + e.getMessage(), e);
                errorReported = true;
                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            }
        }
    }
}
