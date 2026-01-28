package io.github.dandriscoll.devlogs;

import com.cloudbees.plugins.credentials.CredentialsProvider;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import hudson.Extension;
import hudson.console.ConsoleLogFilter;
import hudson.model.Run;
import hudson.model.TaskListener;
import okhttp3.*;
import org.jenkinsci.plugins.plaincredentials.StringCredentials;
import org.jenkinsci.plugins.workflow.steps.*;
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
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

/**
 * Pipeline step that wraps build execution and streams logs to a devlogs instance.
 *
 * Example usage in Jenkinsfile:
 * <pre>
 * // Using collector (recommended):
 * devlogs(url: 'https://collector.example.com', application: 'myapp') {
 *     sh 'make build'
 * }
 *
 * // Using credentials ID:
 * devlogs(credentialsId: 'devlogs-url', application: 'myapp', component: 'build') {
 *     sh 'make build'
 * }
 *
 * // Direct to OpenSearch (legacy):
 * devlogs(url: 'https://admin:password@opensearch.example.com:9200/devlogs-myproject', pipeline: false) {
 *     sh 'make build'
 * }
 * </pre>
 */
public class DevlogsStep extends Step implements Serializable {
    private static final long serialVersionUID = 2L;

    // Pattern to detect environment variable prefixes like "DEVLOGS_OPENSEARCH_URL="
    private static final Pattern ENV_PREFIX_PATTERN = Pattern.compile("^[A-Z][A-Z0-9_]*=");

    private String url;
    private String credentialsId;
    private String index;

    // v2.0 schema fields
    private String application;
    private String component = "jenkins";
    private String environment;
    private String version;

    // Mode: true = collector API, false = direct OpenSearch bulk API
    // Auto-detected from URL: user:pass = OpenSearch, token-only = collector
    private Boolean pipeline = null;

    @DataBoundConstructor
    public DevlogsStep() {
        // Default constructor - url or credentialsId set via setters
    }

    public String getUrl() {
        return url;
    }

    @DataBoundSetter
    public void setUrl(String url) {
        this.url = url;
    }

    public String getCredentialsId() {
        return credentialsId;
    }

    @DataBoundSetter
    public void setCredentialsId(String credentialsId) {
        this.credentialsId = credentialsId;
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

    public Boolean getPipeline() {
        return pipeline;
    }

    @DataBoundSetter
    public void setPipeline(Boolean pipeline) {
        this.pipeline = pipeline;
    }

    /**
     * Detect whether URL is a collector URL or OpenSearch URL.
     *
     * - Collector URL: token in username position only (e.g., http://token@host:port)
     * - OpenSearch URL: both username AND password (e.g., http://user:pass@host:port)
     *
     * @param url The URL to analyze
     * @return true if collector mode, false if OpenSearch mode
     */
    private static boolean isCollectorUrl(String url) {
        try {
            URI uri = new URI(url);
            String userInfo = uri.getUserInfo();
            if (userInfo == null || userInfo.isEmpty()) {
                // No credentials - assume collector mode
                return true;
            }
            // If userInfo contains ':', it has both user and password (OpenSearch)
            // If no ':', it's just a token (collector)
            return !userInfo.contains(":");
        } catch (URISyntaxException e) {
            // Can't parse, assume collector mode
            return true;
        }
    }

    /**
     * Get the effective pipeline mode, auto-detecting from URL if not explicitly set.
     */
    private boolean getEffectivePipeline(String resolvedUrl) {
        if (pipeline != null) {
            return pipeline;
        }
        return isCollectorUrl(resolvedUrl);
    }

    /**
     * Resolve the URL from either direct url parameter or credentialsId lookup.
     *
     * @param run The current build run for credential resolution
     * @return The resolved URL, or null if not configured
     */
    private String resolveUrl(Run<?, ?> run) {
        // Direct URL takes precedence
        if (url != null && !url.trim().isEmpty()) {
            return url;
        }

        // Look up credentialsId
        if (credentialsId != null && !credentialsId.trim().isEmpty()) {
            StringCredentials creds = CredentialsProvider.findCredentialById(
                credentialsId,
                StringCredentials.class,
                run
            );
            if (creds != null) {
                return creds.getSecret().getPlainText();
            }
        }

        return null;
    }

    @Override
    public StepExecution start(StepContext context) throws Exception {
        Run<?, ?> run = context.get(Run.class);
        String resolvedUrl = resolveUrl(run);

        // Derive application from job name if not specified
        String resolvedApplication = application;
        if (resolvedApplication == null || resolvedApplication.trim().isEmpty()) {
            if (run != null) {
                resolvedApplication = run.getParent().getFullName();
            } else {
                resolvedApplication = "jenkins";
            }
        }

        boolean effectivePipeline = getEffectivePipeline(resolvedUrl);
        return new DevlogsStepExecution(context, resolvedUrl, index, credentialsId,
            resolvedApplication, component, environment, version, effectivePipeline);
    }

    @Extension
    public static class DescriptorImpl extends StepDescriptor {

        @Override
        public String getFunctionName() {
            return "devlogs";
        }

        @Nonnull
        @Override
        public String getDisplayName() {
            return "Stream logs to Devlogs";
        }

        @Override
        public boolean takesImplicitBlockArgument() {
            return true;
        }

        @Override
        public Set<? extends Class<?>> getRequiredContext() {
            return Set.of(Run.class, TaskListener.class);
        }
    }

    /**
     * Validates the URL and returns an error message if invalid, or null if valid.
     */
    private static String validateUrl(String url) {
        if (url == null || url.trim().isEmpty()) {
            return null; // Handled separately as missing URL
        }

        String trimmedUrl = url.trim();

        // Check for environment variable prefix (e.g., "DEVLOGS_OPENSEARCH_URL=https://...")
        if (ENV_PREFIX_PATTERN.matcher(trimmedUrl).find()) {
            int equalsPos = trimmedUrl.indexOf('=');
            String prefix = trimmedUrl.substring(0, equalsPos);
            return "URL contains an environment variable prefix '" + prefix + "='. " +
                   "The credential should contain only the URL value, not the variable assignment. " +
                   "Remove the '" + prefix + "=' prefix from your credential.";
        }

        // Check for valid scheme
        if (!trimmedUrl.startsWith("http://") && !trimmedUrl.startsWith("https://")) {
            if (trimmedUrl.contains("://")) {
                String scheme = trimmedUrl.substring(0, trimmedUrl.indexOf("://"));
                return "URL has unsupported scheme '" + scheme + "'. Only 'http' and 'https' are supported.";
            } else {
                return "URL is missing the scheme. Expected format: https://host:port or https://user:pass@host:port/index";
            }
        }

        // Try to parse as URI to validate structure
        try {
            URI uri = new URI(trimmedUrl);
            if (uri.getHost() == null || uri.getHost().isEmpty()) {
                return "URL is missing a host.";
            }
        } catch (URISyntaxException e) {
            return "URL is malformed: " + e.getMessage();
        }

        return null; // Valid
    }

    /**
     * Execution for the devlogs step.
     */
    public static class DevlogsStepExecution extends AbstractStepExecutionImpl {
        private static final long serialVersionUID = 2L;

        private final String url;
        private final String index;
        private final String credentialsId;
        private final String application;
        private final String component;
        private final String environment;
        private final String version;
        private final boolean pipeline;
        private transient DevlogsConsoleLogFilter filter;

        public DevlogsStepExecution(StepContext context, String url, String index, String credentialsId,
                                    String application, String component, String environment,
                                    String version, boolean pipeline) {
            super(context);
            this.url = url;
            this.index = index;
            this.credentialsId = credentialsId;
            this.application = application;
            this.component = component;
            this.environment = environment;
            this.version = version;
            this.pipeline = pipeline;
        }

        private void consoleLog(String message) {
            try {
                TaskListener listener = getContext().get(TaskListener.class);
                if (listener != null) {
                    listener.getLogger().println("[devlogs] " + message);
                }
            } catch (Exception e) {
                // Ignore - can't log to console
            }
        }

        @Override
        public boolean start() throws Exception {
            // Check if URL is missing
            if (url == null || url.trim().isEmpty()) {
                String credInfo = (credentialsId != null && !credentialsId.isEmpty())
                    ? "Credential '" + credentialsId + "' not found or empty."
                    : "No credentialsId or url parameter provided.";
                consoleLog("WARNING: " + credInfo + " Devlogs disabled for this build.");
                getContext().newBodyInvoker().withCallback(BodyExecutionCallback.wrap(getContext())).start();
                return false;
            }

            // Validate URL format
            String validationError = validateUrl(url);
            if (validationError != null) {
                consoleLog("ERROR: " + validationError);
                consoleLog("Devlogs disabled for this build.");
                getContext().newBodyInvoker().withCallback(BodyExecutionCallback.wrap(getContext())).start();
                return false;
            }

            Run<?, ?> run = getContext().get(Run.class);
            if (run == null) {
                throw new IllegalStateException("Run context is not available");
            }

            // Log mode info (mask credentials in URL)
            String maskedUrl = url.replaceAll("://[^:]+:[^@]+@", "://****:****@");
            if (pipeline) {
                consoleLog("Streaming logs to collector: " + maskedUrl);
            } else {
                // Extract index name for logging (direct mode)
                String indexName = index;
                if (indexName == null || indexName.trim().isEmpty()) {
                    int lastSlash = url.lastIndexOf('/');
                    if (lastSlash > 0 && lastSlash < url.length() - 1) {
                        indexName = url.substring(lastSlash + 1);
                    } else {
                        indexName = "devlogs";
                    }
                }
                consoleLog("Streaming logs directly to OpenSearch index '" + indexName + "'");
            }

            // Create and register the log filter
            filter = new DevlogsConsoleLogFilter(url, index, run,
                application, component, environment, version, pipeline);

            getContext().newBodyInvoker()
                .withContext(BodyInvoker.mergeConsoleLogFilters(getContext().get(ConsoleLogFilter.class), filter))
                .withCallback(BodyExecutionCallback.wrap(getContext()))
                .start();

            return false;
        }

        @Override
        public void stop(@Nonnull Throwable cause) throws Exception {
            if (filter != null) {
                filter.close();
            }
            getContext().onFailure(cause);
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

        @Override
        public OutputStream decorateLogger(Run build, OutputStream logger) throws IOException, InterruptedException {
            return new DevlogsOutputStream(logger, url, index, runId, jobName, buildNumber, buildUrl, seq,
                application, component, environment, version, pipeline);
        }

        public void close() {
            // Cleanup if needed
        }
    }

    /**
     * OutputStream that captures log lines and sends them to devlogs.
     */
    private static class DevlogsOutputStream extends OutputStream implements Serializable {
        private static final long serialVersionUID = 2L;
        private static final int BUFFER_SIZE = 8192;
        private static final int BATCH_SIZE = 10;
        private static final long BATCH_TIMEOUT_MS = 10000; // 10 seconds

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
        private boolean errorReported = false; // Only report first error to avoid spam

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
            // Collector URLs (token-only) use Bearer auth
            // OpenSearch URLs (user:password) use Basic auth
            String parsedBaseUrl = url;
            String parsedAuthHeader = null;

            try {
                URI uri = new URI(url);
                String userInfo = uri.getUserInfo();
                if (userInfo != null && !userInfo.isEmpty()) {
                    // Rebuild URL without credentials
                    int port = uri.getPort();
                    String portStr = (port > 0) ? ":" + port : "";
                    String path = uri.getPath();

                    if (pipeline) {
                        // Collector mode: token in username position, use Bearer auth
                        parsedAuthHeader = "Bearer " + userInfo;
                        parsedBaseUrl = uri.getScheme() + "://" + uri.getHost() + portStr + (path != null ? path : "");
                    } else {
                        // OpenSearch mode: user:password, use Basic auth
                        parsedAuthHeader = "Basic " + Base64.getEncoder().encodeToString(
                            userInfo.getBytes(StandardCharsets.UTF_8));

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
            if (errorReported) return; // Only report first error
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
