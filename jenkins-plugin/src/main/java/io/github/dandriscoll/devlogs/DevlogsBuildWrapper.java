package io.github.dandriscoll.devlogs;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import hudson.EnvVars;
import hudson.Extension;
import hudson.FilePath;
import hudson.Launcher;
import hudson.console.ConsoleLogFilter;
import hudson.model.AbstractProject;
import hudson.model.Run;
import hudson.model.TaskListener;
import hudson.tasks.BuildWrapperDescriptor;
import jenkins.tasks.SimpleBuildWrapper;
import okhttp3.*;
import org.jenkinsci.Symbol;
import org.kohsuke.stapler.DataBoundConstructor;
import org.kohsuke.stapler.DataBoundSetter;

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

/**
 * Build wrapper that streams all console output to a devlogs instance.
 *
 * This can be used in declarative pipelines via the options block:
 * <pre>
 * pipeline {
 *     options {
 *         // Collector mode (recommended):
 *         devlogs(url: 'https://collector.example.com', application: 'myapp')
 *
 *         // Direct to OpenSearch (legacy):
 *         devlogs(url: 'https://admin:password@opensearch.example.com:9200/devlogs-myproject', pipeline: false)
 *     }
 *     stages {
 *         stage('Build') {
 *             steps {
 *                 sh 'make build'  // automatically captured
 *             }
 *         }
 *     }
 * }
 * </pre>
 *
 * Or configured via the Jenkins UI on the job configuration page.
 */
public class DevlogsBuildWrapper extends SimpleBuildWrapper implements Serializable {
    private static final long serialVersionUID = 2L;

    private String url;
    private String index;

    // v2.0 schema fields
    private String application;
    private String component = "jenkins";
    private String environment;
    private String version;

    // Mode: true = collector API (default), false = direct OpenSearch bulk API
    private boolean pipeline = true;

    @DataBoundConstructor
    public DevlogsBuildWrapper() {
        // Default constructor for UI configuration
    }

    public String getUrl() {
        return url;
    }

    @DataBoundSetter
    public void setUrl(String url) {
        this.url = url;
    }

    public String getIndex() {
        return index;
    }

    @DataBoundSetter
    public void setIndex(String index) {
        this.index = index;
    }

    public String getApplication() {
        return application;
    }

    @DataBoundSetter
    public void setApplication(String application) {
        this.application = application;
    }

    public String getComponent() {
        return component;
    }

    @DataBoundSetter
    public void setComponent(String component) {
        this.component = component;
    }

    public String getEnvironment() {
        return environment;
    }

    @DataBoundSetter
    public void setEnvironment(String environment) {
        this.environment = environment;
    }

    public String getVersion() {
        return version;
    }

    @DataBoundSetter
    public void setVersion(String version) {
        this.version = version;
    }

    public boolean getPipeline() {
        return pipeline;
    }

    @DataBoundSetter
    public void setPipeline(boolean pipeline) {
        this.pipeline = pipeline;
    }

    @Override
    public void setUp(Context context, Run<?, ?> build, FilePath workspace,
                      Launcher launcher, TaskListener listener, EnvVars initialEnvironment)
            throws IOException, InterruptedException {
        // Resolve environment variables in URL
        String resolvedUrl = initialEnvironment.expand(url);

        if (resolvedUrl == null || resolvedUrl.trim().isEmpty()) {
            listener.getLogger().println("[devlogs] No URL configured, skipping log streaming");
            return;
        }

        if (pipeline) {
            listener.getLogger().println("[devlogs] Streaming logs to collector: " + maskUrl(resolvedUrl));
        } else {
            listener.getLogger().println("[devlogs] Streaming logs directly to OpenSearch: " + maskUrl(resolvedUrl));
        }
    }

    @Override
    public ConsoleLogFilter createLoggerDecorator(@Nonnull Run<?, ?> build) {
        if (url == null || url.trim().isEmpty()) {
            return null;
        }

        // Derive application from job name if not specified
        String resolvedApplication = application;
        if (resolvedApplication == null || resolvedApplication.trim().isEmpty()) {
            resolvedApplication = build.getParent().getFullName();
        }

        return new DevlogsConsoleLogFilter(url, index, build,
            resolvedApplication, component, environment, version, pipeline);
    }

    /**
     * Mask credentials in URL for display
     */
    private String maskUrl(String url) {
        return url.replaceAll("://[^:]+:[^@]+@", "://****:****@");
    }

    @Extension
    @Symbol("devlogs")
    public static class DescriptorImpl extends BuildWrapperDescriptor {

        @Nonnull
        @Override
        public String getDisplayName() {
            return "Stream logs to Devlogs";
        }

        @Override
        public boolean isApplicable(AbstractProject<?, ?> item) {
            return true;
        }
    }

    /**
     * Console log filter that intercepts and streams logs to devlogs.
     */
    private static class DevlogsConsoleLogFilter extends ConsoleLogFilter implements Serializable {
        private static final long serialVersionUID = 2L;

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
        private final AtomicInteger seq = new AtomicInteger(0);

        public DevlogsConsoleLogFilter(String url, String index, Run<?, ?> run,
                                       String application, String component,
                                       String environment, String version, boolean pipeline) {
            this.url = url;
            this.application = application;
            this.component = component;
            this.environment = environment;
            this.version = version;
            this.pipeline = pipeline;

            // Extract index from URL if not provided separately (for direct mode)
            if (index == null || index.trim().isEmpty()) {
                this.index = extractIndexFromUrl(url);
            } else {
                this.index = index;
            }

            this.runId = run.getExternalizableId();
            this.jobName = run.getParent().getFullName();
            this.buildNumber = run.getNumber();
            this.buildUrl = run.getUrl();
        }

        private String extractIndexFromUrl(String url) {
            try {
                int lastSlash = url.lastIndexOf('/');
                if (lastSlash > 0 && lastSlash < url.length() - 1) {
                    String potential = url.substring(lastSlash + 1);
                    // Don't treat API paths as index names
                    if (!potential.startsWith("v1") && !potential.equals("logs")) {
                        return potential;
                    }
                }
            } catch (Exception e) {
                // Fall back to default
            }
            return "devlogs";
        }

        @SuppressWarnings("rawtypes")
        @Override
        public OutputStream decorateLogger(Run build, OutputStream logger)
                throws IOException, InterruptedException {
            return new DevlogsOutputStream(logger, url, index, runId, jobName, buildNumber, buildUrl, seq,
                application, component, environment, version, pipeline);
        }
    }

    /**
     * OutputStream that captures log lines and sends them to devlogs.
     */
    private static class DevlogsOutputStream extends OutputStream implements Serializable {
        private static final long serialVersionUID = 2L;
        private static final int BUFFER_SIZE = 8192;
        private static final int BATCH_SIZE = 10;
        private static final long BATCH_TIMEOUT_MS = 10000;

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

        private transient OkHttpClient client;
        private transient Gson gson;

        private static final DateTimeFormatter ISO_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC);

        public DevlogsOutputStream(OutputStream delegate, String url, String index, String runId,
                                   String jobName, int buildNumber, String buildUrl, AtomicInteger seq,
                                   String application, String component, String environment,
                                   String version, boolean pipeline) {
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
                    // Build auth header from credentials
                    parsedAuthHeader = "Basic " + Base64.getEncoder().encodeToString(
                        userInfo.getBytes(StandardCharsets.UTF_8));

                    // Rebuild URL without credentials
                    int port = uri.getPort();
                    String portStr = (port > 0) ? ":" + port : "";
                    String path = uri.getPath();

                    if (pipeline) {
                        // For collector mode, keep the base path
                        parsedBaseUrl = uri.getScheme() + "://" + uri.getHost() + portStr + (path != null ? path : "");
                    } else {
                        // For direct mode, remove trailing path segment (index name)
                        if (path != null && path.lastIndexOf('/') > 0) {
                            path = path.substring(0, path.lastIndexOf('/'));
                        } else {
                            path = "";
                        }
                        parsedBaseUrl = uri.getScheme() + "://" + uri.getHost() + portStr + path;
                    }
                } else {
                    if (!pipeline) {
                        // No credentials in URL, extract base URL the simple way (direct mode)
                        int lastSlash = url.lastIndexOf('/');
                        if (lastSlash > 0) {
                            parsedBaseUrl = url.substring(0, lastSlash);
                        }
                    }
                }
            } catch (URISyntaxException e) {
                if (!pipeline) {
                    // Fall back to simple extraction (direct mode only)
                    int lastSlash = url.lastIndexOf('/');
                    if (lastSlash > 0) {
                        parsedBaseUrl = url.substring(0, lastSlash);
                    }
                }
            }

            this.baseUrl = parsedBaseUrl;
            this.authHeader = parsedAuthHeader;

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

            buffer[bufferPos++] = (byte) b;

            if (b == '\n' || bufferPos >= BUFFER_SIZE) {
                processBuffer();
            }
        }

        @Override
        public void write(byte[] b, int off, int len) throws IOException {
            delegate.write(b, off, len);

            for (int i = 0; i < len; i++) {
                buffer[bufferPos++] = b[off + i];

                if (b[off + i] == '\n' || bufferPos >= BUFFER_SIZE) {
                    processBuffer();
                }
            }
        }

        @Override
        public void flush() throws IOException {
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
            flush();
            delegate.close();
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

            try {
                initTransients();

                long currentTime = System.currentTimeMillis();
                if (batchCount > 0 && (currentTime - lastBatchTime) >= BATCH_TIMEOUT_MS) {
                    flushBatch();
                }

                if (pipeline) {
                    // Collector mode: v2.0 schema
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

                    // Build metadata goes in fields
                    JsonObject fields = new JsonObject();
                    fields.addProperty("run_id", runId);
                    fields.addProperty("job", jobName);
                    fields.addProperty("build_number", buildNumber);
                    fields.addProperty("build_url", buildUrl);
                    fields.addProperty("seq", seq.incrementAndGet());
                    doc.add("fields", fields);

                    collectorBatch.add(doc);
                } else {
                    // Direct mode: v2.0 schema with bulk API format
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

                    // Build metadata in fields
                    JsonObject fields = new JsonObject();
                    fields.addProperty("run_id", runId);
                    fields.addProperty("job", jobName);
                    fields.addProperty("build_number", buildNumber);
                    fields.addProperty("build_url", buildUrl);
                    fields.addProperty("seq", seq.incrementAndGet());
                    doc.add("fields", fields);

                    // Source info (v2.0 schema)
                    JsonObject source = new JsonObject();
                    source.addProperty("logger", "jenkins");
                    doc.add("source", source);

                    // Process info (v2.0 schema)
                    JsonObject process = new JsonObject();
                    process.addProperty("id", buildNumber);
                    process.addProperty("thread", seq.get());
                    doc.add("process", process);

                    batchBuffer.append("{\"index\":{\"_index\":\"").append(index).append("\"}}\n");
                    batchBuffer.append(gson.toJson(doc)).append("\n");
                }

                batchCount++;

                if (batchCount == 1) {
                    lastBatchTime = currentTime;
                }

                if (batchCount >= BATCH_SIZE) {
                    flushBatch();
                }
            } catch (Exception e) {
                // Don't fail the build if logging fails
            }
        }

        private void consoleError(String message) {
            if (errorReported) return;
            errorReported = true;
            try {
                String line = "[devlogs] " + message + "\n";
                delegate.write(line.getBytes(StandardCharsets.UTF_8));
                delegate.flush();
            } catch (IOException e) {
                // Can't write to console
            }
        }

        private void flushBatch() {
            if (batchCount == 0) return;

            try {
                initTransients();

                Request request;

                if (pipeline) {
                    // Collector mode: POST to /v1/logs with JSON array
                    String collectorUrl = baseUrl.endsWith("/") ? baseUrl + "v1/logs" : baseUrl + "/v1/logs";

                    JsonObject payload = new JsonObject();
                    payload.add("records", collectorBatch);

                    RequestBody body = RequestBody.create(
                        gson.toJson(payload),
                        MediaType.parse("application/json")
                    );

                    Request.Builder requestBuilder = new Request.Builder()
                        .url(collectorUrl)
                        .post(body);

                    if (authHeader != null) {
                        requestBuilder.addHeader("Authorization", authHeader);
                    }

                    request = requestBuilder.build();

                    // Clear collector batch
                    while (collectorBatch.size() > 0) {
                        collectorBatch.remove(0);
                    }
                } else {
                    // Direct mode: POST to /_bulk with NDJSON
                    String bulkUrl = baseUrl + "/_bulk";

                    RequestBody body = RequestBody.create(
                        batchBuffer.toString(),
                        MediaType.parse("application/x-ndjson")
                    );

                    Request.Builder requestBuilder = new Request.Builder()
                        .url(bulkUrl)
                        .post(body);

                    if (authHeader != null) {
                        requestBuilder.addHeader("Authorization", authHeader);
                    }

                    request = requestBuilder.build();
                }

                try (Response response = client.newCall(request).execute()) {
                    if (!response.isSuccessful()) {
                        String responseBody = response.body() != null ? response.body().string() : "";
                        String detail = responseBody.length() > 100 ? responseBody.substring(0, 100) + "..." : responseBody;
                        String target = pipeline ? "collector" : "OpenSearch";
                        consoleError("ERROR: Failed to send logs to " + target + ". HTTP " + response.code() + ": " + detail);
                    }
                }

                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            } catch (Exception e) {
                String target = pipeline ? "collector" : "OpenSearch";
                consoleError("ERROR: Failed to send logs to " + target + ": " + e.getMessage());
                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            }
        }
    }
}
