package io.github.dandriscoll.devlogs;

import com.cloudbees.plugins.credentials.CredentialsProvider;
import hudson.Extension;
import hudson.model.Run;
import hudson.model.TaskListener;
import org.jenkinsci.plugins.plaincredentials.StringCredentials;
import org.jenkinsci.plugins.workflow.steps.*;
import org.kohsuke.stapler.DataBoundConstructor;
import org.kohsuke.stapler.DataBoundSetter;

import javax.annotation.Nonnull;
import java.io.Serializable;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Set;
import java.util.logging.Level;
import java.util.logging.Logger;
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
    private static final String VERSION = "2.0.2";
    private static final Logger LOGGER = Logger.getLogger(DevlogsStep.class.getName());
    private static final String DEBUG_PREFIX = "[DEVLOGS-DEBUG] ";

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
        if (url == null || url.isEmpty()) {
            return true;  // Default to collector mode if no URL
        }
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
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "resolveUrl() called, url=" + (url != null ? "[set]" : "null") +
            ", credentialsId=" + (credentialsId != null ? credentialsId : "null"));

        // Direct URL takes precedence
        if (url != null && !url.trim().isEmpty()) {
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "resolveUrl() using direct URL");
            return url;
        }

        // Look up credentialsId
        if (credentialsId != null && !credentialsId.trim().isEmpty()) {
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "resolveUrl() looking up credentialsId: " + credentialsId);
            StringCredentials creds = CredentialsProvider.findCredentialById(
                credentialsId,
                StringCredentials.class,
                run
            );
            if (creds != null) {
                LOGGER.log(Level.INFO, DEBUG_PREFIX + "resolveUrl() found credentials, returning URL");
                return creds.getSecret().getPlainText();
            } else {
                LOGGER.log(Level.WARNING, DEBUG_PREFIX + "resolveUrl() credentials NOT FOUND for id: " + credentialsId);
            }
        }

        LOGGER.log(Level.WARNING, DEBUG_PREFIX + "resolveUrl() returning null - no URL configured");
        return null;
    }

    @Override
    public StepExecution start(StepContext context) throws Exception {
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStep.start() called");
        Run<?, ?> run = context.get(Run.class);
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStep.start() run=" +
            (run != null ? run.getFullDisplayName() : "null"));
        String resolvedUrl = resolveUrl(run);
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStep.start() resolvedUrl=" +
            (resolvedUrl != null ? "[resolved]" : "null"));

        // Derive application from job name if not specified
        String resolvedApplication = application;
        if (resolvedApplication == null || resolvedApplication.trim().isEmpty()) {
            if (run != null) {
                resolvedApplication = run.getParent().getFullName();
            } else {
                resolvedApplication = "jenkins";
            }
        }
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStep.start() resolvedApplication=" + resolvedApplication);

        boolean effectivePipeline = getEffectivePipeline(resolvedUrl);
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStep.start() effectivePipeline=" + effectivePipeline +
            ", component=" + component + ", index=" + index);
        LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStep.start() returning DevlogsStepExecution");
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
        private static final String DEBUG_PREFIX = "[DEVLOGS-DEBUG] ";

        private final String url;
        private final String index;
        private final String credentialsId;
        private final String application;
        private final String component;
        private final String environment;
        private final String version;
        private final boolean pipeline;

        public DevlogsStepExecution(StepContext context, String url, String index, String credentialsId,
                                    String application, String component, String environment,
                                    String version, boolean pipeline) {
            super(context);
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStepExecution constructor called");
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "  url=" + (url != null ? "[set]" : "null"));
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "  index=" + index);
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "  application=" + application);
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "  component=" + component);
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "  pipeline=" + pipeline);
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
                    LOGGER.log(Level.INFO, DEBUG_PREFIX + "consoleLog() wrote: " + message);
                } else {
                    LOGGER.log(Level.WARNING, DEBUG_PREFIX + "consoleLog() - TaskListener is null, message: " + message);
                }
            } catch (Exception e) {
                LOGGER.log(Level.WARNING, DEBUG_PREFIX + "consoleLog() exception: " + e.getMessage());
            }
        }

        @Override
        public boolean start() throws Exception {
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStepExecution.start() called");

            // Check if URL is missing
            if (url == null || url.trim().isEmpty()) {
                String credInfo = (credentialsId != null && !credentialsId.isEmpty())
                    ? "Credential '" + credentialsId + "' not found or empty."
                    : "No credentialsId or url parameter provided.";
                consoleLog("WARNING: " + credInfo + " Devlogs disabled for this build.");
                LOGGER.log(Level.WARNING, DEBUG_PREFIX + "DevlogsStepExecution.start() - URL missing, devlogs disabled");
                getContext().newBodyInvoker().withCallback(BodyExecutionCallback.wrap(getContext())).start();
                return false;
            }

            // Validate URL format
            String validationError = validateUrl(url);
            if (validationError != null) {
                consoleLog("ERROR: " + validationError);
                consoleLog("Devlogs disabled for this build.");
                LOGGER.log(Level.WARNING, DEBUG_PREFIX + "DevlogsStepExecution.start() - URL validation failed: " + validationError);
                getContext().newBodyInvoker().withCallback(BodyExecutionCallback.wrap(getContext())).start();
                return false;
            }

            Run<?, ?> run = getContext().get(Run.class);
            if (run == null) {
                LOGGER.log(Level.SEVERE, DEBUG_PREFIX + "DevlogsStepExecution.start() - Run context is null!");
                throw new IllegalStateException("Run context is not available");
            }
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStepExecution.start() - Run: " + run.getFullDisplayName());

            // Log step start with version
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "Devlogs plugin v" + VERSION + " starting for build " +
                run.getParent().getFullName() + "#" + run.getNumber());
            consoleLog("Devlogs plugin v" + VERSION + " starting");

            // Ensure DevlogsJobProperty is set on the job for LogStorageFactory
            hudson.model.Job<?, ?> job = run.getParent();
            DevlogsJobProperty existingProp = job.getProperty(DevlogsJobProperty.class);
            if (existingProp == null) {
                LOGGER.log(Level.INFO, DEBUG_PREFIX + "Setting DevlogsJobProperty on job for future builds");
                try {
                    DevlogsJobProperty prop = new DevlogsJobProperty(credentialsId);
                    prop.setApplication(application);
                    prop.setComponent(component);
                    prop.setEnvironment(environment);
                    job.addProperty(prop);
                    LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsJobProperty set successfully");
                } catch (Exception e) {
                    LOGGER.log(Level.WARNING, DEBUG_PREFIX + "Failed to set DevlogsJobProperty: " + e.getMessage());
                }
            } else {
                LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsJobProperty already present on job");
            }

            // Check if LogStorageFactory is already handling this build
            // (DevlogsLogStorage is active - no need for TaskListenerDecorator)
            boolean logStorageActive = DevlogsLogStorage.isActiveForBuild(run.getExternalizableId());
            if (logStorageActive) {
                LOGGER.log(Level.INFO, DEBUG_PREFIX + "LogStorageFactory is active - skipping TaskListenerDecorator");
                consoleLog("Log streaming active via LogStorage (full capture mode)");
                final String buildId = run.getParent().getFullName() + "#" + run.getNumber();
                getContext().newBodyInvoker()
                    .withCallback(new BodyExecutionCallback() {
                        @Override
                        public void onSuccess(StepContext context, Object result) {
                            LOGGER.log(Level.INFO, DEBUG_PREFIX + "Build completed successfully: " + buildId);
                            context.onSuccess(result);
                        }

                        @Override
                        public void onFailure(StepContext context, Throwable t) {
                            LOGGER.log(Level.INFO, DEBUG_PREFIX + "Build completed with failure: " + buildId);
                            context.onFailure(t);
                        }
                    })
                    .start();
                return false;
            }

            // LogStorageFactory not active - fall back to TaskListenerDecorator
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "LogStorageFactory not active - using TaskListenerDecorator fallback");

            // Log mode info (mask credentials in URL)
            String maskedUrl = url.replaceAll("://[^:]+:[^@]+@", "://****:****@");
            if (pipeline) {
                consoleLog("Streaming logs to collector: " + maskedUrl);
            } else {
                String indexName = index;
                if (indexName == null || indexName.trim().isEmpty()) {
                    int lastSlash = url.lastIndexOf('/');
                    if (lastSlash > 0 && lastSlash < url.length() - 1) {
                        indexName = url.substring(lastSlash + 1);
                    } else {
                        indexName = "devlogs";
                    }
                }
                consoleLog("Streaming logs directly to OpenSearch index '" + indexName + "' (partial capture - next build will use full capture)");
            }

            // Create action with config and decorator
            DevlogsAction action = new DevlogsAction(url, index, run,
                application, component, environment, version, pipeline);
            run.addAction(action);

            DevlogsGlobalDecorator decorator = new DevlogsGlobalDecorator(action);

            org.jenkinsci.plugins.workflow.log.TaskListenerDecorator existingDecorator =
                getContext().get(org.jenkinsci.plugins.workflow.log.TaskListenerDecorator.class);

            final String buildId = run.getParent().getFullName() + "#" + run.getNumber();

            getContext().newBodyInvoker()
                .withContext(org.jenkinsci.plugins.workflow.log.TaskListenerDecorator.merge(
                    existingDecorator,
                    decorator))
                .withCallback(new BodyExecutionCallback() {
                    @Override
                    public void onSuccess(StepContext context, Object result) {
                        LOGGER.log(Level.INFO, DEBUG_PREFIX + "Build completed successfully: " + buildId);
                        try {
                            TaskListener listener = context.get(TaskListener.class);
                            if (listener != null) {
                                listener.getLogger().println("[devlogs] Build complete, logs streamed successfully");
                            }
                        } catch (Exception e) {
                            // ignore
                        }
                        context.onSuccess(result);
                    }

                    @Override
                    public void onFailure(StepContext context, Throwable t) {
                        LOGGER.log(Level.INFO, DEBUG_PREFIX + "Build completed with failure: " + buildId);
                        try {
                            TaskListener listener = context.get(TaskListener.class);
                            if (listener != null) {
                                listener.getLogger().println("[devlogs] Build complete (with failure), logs streamed");
                            }
                        } catch (Exception e) {
                            // ignore
                        }
                        context.onFailure(t);
                    }
                })
                .start();

            LOGGER.log(Level.INFO, DEBUG_PREFIX + "Body invoker started, returning false (async)");
            return false;
        }

        @Override
        public void stop(@Nonnull Throwable cause) throws Exception {
            LOGGER.log(Level.INFO, DEBUG_PREFIX + "DevlogsStepExecution.stop() called: " + cause.getMessage());
            LOGGER.log(Level.INFO, "Devlogs plugin v" + VERSION + " stopped");
            getContext().onFailure(cause);
        }
    }
}
