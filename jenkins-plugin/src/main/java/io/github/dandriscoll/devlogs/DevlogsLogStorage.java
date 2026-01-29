package io.github.dandriscoll.devlogs;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import hudson.console.AnnotatedLargeText;
import hudson.model.BuildListener;
import hudson.model.Run;
import hudson.model.TaskListener;
import okhttp3.*;
import org.jenkinsci.plugins.workflow.flow.FlowExecutionOwner;
import org.jenkinsci.plugins.workflow.graph.FlowNode;
import org.jenkinsci.plugins.workflow.log.FileLogStorage;
import org.jenkinsci.plugins.workflow.log.LogStorage;

import javax.annotation.Nonnull;
import java.io.*;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * LogStorage implementation that wraps FileLogStorage and tees output to OpenSearch.
 * This captures ALL pipeline output including [Pipeline] annotations.
 */
public class DevlogsLogStorage implements LogStorage {
    private static final Logger LOGGER = Logger.getLogger(DevlogsLogStorage.class.getName());
    private static final String DEBUG_PREFIX = "[DEVLOGS-DEBUG] ";
    private static final DateTimeFormatter ISO_FORMATTER =
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC);

    private final LogStorage delegate;
    private final String url;
    private final String baseUrl;
    private final String index;
    private final String authHeader;
    private final String application;
    private final String component;
    private final String environment;
    private final String jobName;
    private final int buildNumber;
    private final String buildUrl;
    private final String buildId;
    private final boolean pipelineMode;
    private final Runnable cleanupCallback;
    private final AtomicInteger seq = new AtomicInteger(0);

    // Track active instances for coordination with DevlogsStep
    private static final Map<String, Boolean> activeBuilds = new ConcurrentHashMap<>();

    private transient OkHttpClient client;
    private transient Gson gson;

    public DevlogsLogStorage(FlowExecutionOwner owner, String url, String application,
                             String component, String environment, String jobName,
                             int buildNumber, String buildUrl, String buildId,
                             Runnable cleanupCallback) {
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsLogStorage constructor for build " + buildNumber);

        // Get the log file from the build directory
        File logFile;
        try {
            Run<?, ?> run = (Run<?, ?>) owner.getExecutable();
            logFile = new File(run.getRootDir(), "log");
        } catch (IOException e) {
            LOGGER.log(Level.WARNING, DEBUG_PREFIX + "Could not get build directory, using fallback", e);
            logFile = new File("devlogs-fallback-" + buildNumber + ".log");
        }
        this.delegate = FileLogStorage.forFile(logFile);
        this.url = url;
        this.application = application;
        this.component = component != null ? component : "jenkins";
        this.environment = environment;
        this.jobName = jobName;
        this.buildNumber = buildNumber;
        this.buildUrl = buildUrl;
        this.buildId = buildId;
        this.cleanupCallback = cleanupCallback;

        // Parse URL to extract credentials and determine mode
        String parsedBaseUrl = url;
        String parsedIndex = "devlogs";
        String parsedAuthHeader = null;
        boolean parsedPipelineMode = true;

        try {
            URI uri = new URI(url);
            String userInfo = uri.getUserInfo();
            int port = uri.getPort();
            String portStr = (port > 0) ? ":" + port : "";
            String path = uri.getPath();

            if (userInfo != null && !userInfo.isEmpty()) {
                if (userInfo.contains(":")) {
                    // OpenSearch mode: user:pass
                    parsedPipelineMode = false;
                    parsedAuthHeader = "Basic " + Base64.getEncoder().encodeToString(
                        userInfo.getBytes(StandardCharsets.UTF_8));

                    // Extract index from path
                    if (path != null && path.length() > 1) {
                        parsedIndex = path.substring(path.lastIndexOf('/') + 1);
                        path = path.substring(0, path.lastIndexOf('/'));
                        if (path.isEmpty()) path = "";
                    }
                    parsedBaseUrl = uri.getScheme() + "://" + uri.getHost() + portStr + path;
                } else {
                    // Collector mode: token only
                    parsedPipelineMode = true;
                    parsedAuthHeader = "Bearer " + userInfo;
                    parsedBaseUrl = uri.getScheme() + "://" + uri.getHost() + portStr + (path != null ? path : "");
                }
            }
        } catch (URISyntaxException e) {
            LOGGER.log(Level.WARNING, DEBUG_PREFIX + "URL parse error: " + e.getMessage());
        }

        this.baseUrl = parsedBaseUrl;
        this.index = parsedIndex;
        this.authHeader = parsedAuthHeader;
        this.pipelineMode = parsedPipelineMode;

        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsLogStorage created: baseUrl=" + parsedBaseUrl +
            ", index=" + parsedIndex + ", pipelineMode=" + parsedPipelineMode);

        activeBuilds.put(buildId, true);
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

    @Nonnull
    @Override
    public BuildListener overallListener() throws IOException, InterruptedException {
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "overallListener() called for build " + buildNumber);
        BuildListener delegateListener = delegate.overallListener();
        return new DevlogsBuildListener(delegateListener, this, "overall");
    }

    @Nonnull
    @Override
    public TaskListener nodeListener(@Nonnull FlowNode node) throws IOException, InterruptedException {
        LOGGER.log(Level.FINE, DEBUG_PREFIX + "nodeListener() called for node " + node.getId());
        TaskListener delegateListener = delegate.nodeListener(node);
        return new DevlogsTaskListener(delegateListener, this, node.getId());
    }

    @Nonnull
    @Override
    public AnnotatedLargeText<FlowExecutionOwner.Executable> overallLog(
            @Nonnull FlowExecutionOwner.Executable build, boolean complete) {
        // Delegate to FileLogStorage for reading
        return delegate.overallLog(build, complete);
    }

    @Nonnull
    @Override
    public AnnotatedLargeText<FlowNode> stepLog(@Nonnull FlowNode node, boolean complete) {
        // Delegate to FileLogStorage for reading
        return delegate.stepLog(node, complete);
    }

    /**
     * Send a log line to OpenSearch.
     */
    void sendLine(String line, String timestamp, String nodeId) {
        if (line.trim().isEmpty()) return;

        int seqNum = seq.incrementAndGet();

        // Log first few lines for debugging
        if (seqNum <= 5 || seqNum % 50 == 0) {
            String preview = line.length() > 60 ? line.substring(0, 60) + "..." : line;
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "sendLine() seq=" + seqNum + ": " + preview);
        }

        try {
            initTransients();

            JsonObject doc = new JsonObject();
            doc.addProperty("timestamp", timestamp);
            doc.addProperty("message", line);
            doc.addProperty("level", "info");
            doc.addProperty("application", application);
            doc.addProperty("component", component);
            doc.addProperty("area", jobName);

            if (environment != null && !environment.isEmpty()) {
                doc.addProperty("environment", environment);
            }

            JsonObject fields = new JsonObject();
            fields.addProperty("run_id", buildId);
            fields.addProperty("job", jobName);
            fields.addProperty("build_number", buildNumber);
            fields.addProperty("build_url", buildUrl);
            fields.addProperty("seq", seqNum);
            if (nodeId != null) {
                fields.addProperty("node_id", nodeId);
            }
            doc.add("fields", fields);

            // Add flat fields for OpenSearch direct mode
            if (!pipelineMode) {
                doc.addProperty("doc_type", "log_entry");
                doc.addProperty("logger", "jenkins");
                doc.addProperty("process", buildNumber);
                doc.addProperty("thread", seqNum);
            }

            // Send immediately (no batching for reliability)
            String targetUrl;
            RequestBody body;
            MediaType mediaType;

            if (pipelineMode) {
                targetUrl = baseUrl.endsWith("/") ? baseUrl + "v1/logs" : baseUrl + "/v1/logs";
                com.google.gson.JsonArray records = new com.google.gson.JsonArray();
                records.add(doc);
                JsonObject payload = new JsonObject();
                payload.add("records", records);
                body = RequestBody.create(gson.toJson(payload), MediaType.parse("application/json"));
            } else {
                targetUrl = baseUrl + "/_bulk";
                String ndjson = "{\"index\":{\"_index\":\"" + index + "\"}}\n" + gson.toJson(doc) + "\n";
                body = RequestBody.create(ndjson, MediaType.parse("application/x-ndjson"));
            }

            Request.Builder requestBuilder = new Request.Builder()
                .url(targetUrl)
                .post(body);

            if (authHeader != null) {
                requestBuilder.addHeader("Authorization", authHeader);
            }

            Request request = requestBuilder.build();

            try (Response response = client.newCall(request).execute()) {
                if (!response.isSuccessful()) {
                    String responseBody = response.body() != null ? response.body().string() : "";
                    String preview = responseBody.length() > 100 ? responseBody.substring(0, 100) : responseBody;
                    LOGGER.log(Level.WARNING, DEBUG_PREFIX + "Send failed HTTP " + response.code() + ": " + preview);
                }
            }

        } catch (Exception e) {
            LOGGER.log(Level.WARNING, DEBUG_PREFIX + "sendLine() exception: " + e.getMessage());
        }
    }

    /**
     * Check if LogStorage is active for a given build.
     */
    static boolean isActiveForBuild(String buildId) {
        return activeBuilds.containsKey(buildId);
    }

    /**
     * Called when the build completes to clean up.
     */
    void cleanup() {
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "cleanup() called for build " + buildNumber +
            ", total lines sent: " + seq.get());
        activeBuilds.remove(buildId);
        if (cleanupCallback != null) {
            cleanupCallback.run();
        }
    }

    /**
     * Format a timestamp in ISO format.
     */
    static String formatTimestamp() {
        return ISO_FORMATTER.format(Instant.now());
    }

    /**
     * BuildListener that tees output to OpenSearch.
     */
    private static class DevlogsBuildListener implements BuildListener, Closeable {
        private static final long serialVersionUID = 1L;

        private final BuildListener delegate;
        private final DevlogsLogStorage storage;
        private final DevlogsOutputStream outputStream;
        private final PrintStream printStream;

        DevlogsBuildListener(BuildListener delegate, DevlogsLogStorage storage, String nodeId) {
            this.delegate = delegate;
            this.storage = storage;
            this.outputStream = new DevlogsOutputStream(delegate.getLogger(), storage, nodeId);
            this.printStream = new PrintStream(outputStream, true, StandardCharsets.UTF_8);
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsBuildListener created for node " + nodeId +
                ", delegate class: " + delegate.getClass().getName());
        }

        @Nonnull
        @Override
        public PrintStream getLogger() {
            return printStream;
        }

        @Override
        public void close() throws IOException {
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsBuildListener.close() called, " +
                "total lines from overall: " + outputStream.lineCount);
            outputStream.close();
            if (delegate instanceof Closeable) {
                ((Closeable) delegate).close();
            }
            storage.cleanup();
        }
    }

    /**
     * TaskListener that tees output to OpenSearch.
     */
    private static class DevlogsTaskListener implements TaskListener, Closeable {
        private static final long serialVersionUID = 1L;

        private final TaskListener delegate;
        private final DevlogsLogStorage storage;
        private final DevlogsOutputStream outputStream;
        private final PrintStream printStream;

        DevlogsTaskListener(TaskListener delegate, DevlogsLogStorage storage, String nodeId) {
            this.delegate = delegate;
            this.storage = storage;
            this.outputStream = new DevlogsOutputStream(delegate.getLogger(), storage, nodeId);
            this.printStream = new PrintStream(outputStream, true, StandardCharsets.UTF_8);
            LOGGER.log(Level.FINE, DEBUG_PREFIX + "DevlogsTaskListener created for node " + nodeId);
        }

        @Nonnull
        @Override
        public PrintStream getLogger() {
            return printStream;
        }

        @Override
        public void close() throws IOException {
            LOGGER.log(Level.FINE, DEBUG_PREFIX + "DevlogsTaskListener.close() for node, lines: " + outputStream.lineCount);
            outputStream.close();
            if (delegate instanceof Closeable) {
                ((Closeable) delegate).close();
            }
        }
    }

    /**
     * OutputStream that tees to both delegate and OpenSearch.
     */
    private static class DevlogsOutputStream extends OutputStream {
        private final OutputStream delegate;
        private final DevlogsLogStorage storage;
        private final String nodeId;
        private final StringBuilder lineBuffer = new StringBuilder();
        private String currentLineTimestamp = null;
        int lineCount = 0;
        long byteCount = 0;

        DevlogsOutputStream(OutputStream delegate, DevlogsLogStorage storage, String nodeId) {
            this.delegate = delegate;
            this.storage = storage;
            this.nodeId = nodeId;
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream created for node=" + nodeId +
                ", delegate=" + delegate.getClass().getName());
        }

        @Override
        public void write(int b) throws IOException {
            delegate.write(b);
            byteCount++;

            if (b == '\n') {
                if (lineBuffer.length() > 0) {
                    lineCount++;
                    String timestamp = currentLineTimestamp != null ? currentLineTimestamp : formatTimestamp();
                    storage.sendLine(lineBuffer.toString(), timestamp, nodeId);
                    lineBuffer.setLength(0);
                    currentLineTimestamp = null;
                }
            } else {
                if (lineBuffer.length() == 0 && currentLineTimestamp == null) {
                    currentLineTimestamp = formatTimestamp();
                }
                lineBuffer.append((char) b);
            }
        }

        @Override
        public void write(byte[] b, int off, int len) throws IOException {
            delegate.write(b, off, len);
            byteCount += len;

            for (int i = 0; i < len; i++) {
                byte c = b[off + i];
                if (c == '\n') {
                    if (lineBuffer.length() > 0) {
                        lineCount++;
                        String timestamp = currentLineTimestamp != null ? currentLineTimestamp : formatTimestamp();
                        storage.sendLine(lineBuffer.toString(), timestamp, nodeId);
                        lineBuffer.setLength(0);
                        currentLineTimestamp = null;
                    }
                } else {
                    if (lineBuffer.length() == 0 && currentLineTimestamp == null) {
                        currentLineTimestamp = formatTimestamp();
                    }
                    lineBuffer.append((char) c);
                }
            }
        }

        @Override
        public void flush() throws IOException {
            delegate.flush();
            // Flush any remaining content in buffer
            if (lineBuffer.length() > 0) {
                String timestamp = currentLineTimestamp != null ? currentLineTimestamp : formatTimestamp();
                storage.sendLine(lineBuffer.toString(), timestamp, nodeId);
                lineBuffer.setLength(0);
                currentLineTimestamp = null;
            }
        }

        @Override
        public void close() throws IOException {
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsOutputStream.close() node=" + nodeId +
                ", bytes=" + byteCount + ", lines=" + lineCount);
            flush();
            delegate.close();
        }
    }
}
