# Jarvis Xerife — mapa de módulos (gerado automaticamente)
> Diretórios e assinaturas encontrados no checkout. Este mapa não representa status de execução, disponibilidade ou autorização.

```mermaid
graph LR
    classDef core fill:#1a1f25,stroke:#00ff00,color:#fff,stroke-width:2px;
    classDef adapter fill:#1a1f25,stroke:#007bff,color:#fff;
    classDef port fill:#1a1f25,stroke:#ffa500,color:#fff,stroke-dasharray: 5 5;
    classDef support fill:#2d333b,stroke:#6c757d,color:#aaa;
    app["<b>app</b><br/><hr/>📄 bootstrap_edge.py: main<br/>📄 container.py: Container"]
    class app support
    app_adapters["<b>adapters</b><br/><hr/>📄 jarvis_return_activity.py: LASTINPUTINFO, get_idle_seconds"]
    class app_adapters adapter
    app --> app_adapters
    app_adapters_api["<b>api</b><br/><hr/>📄 voice_endpoint.py: voice_stream"]
    class app_adapters_api adapter
    app_adapters --> app_adapters_api
    app_adapters_edge["<b>edge</b><br/><hr/>📄 active_recruiter_adapter.py: ActiveRecruiterAdapter, execute<br/>📄 android_accessibility_client.py: accessibility_token, accessibility_endpoint, validate_accessibility_action<br/>📄 android_host_status.py: android_device_status, android_battery_status<br/>📄 android_mcp_observability.py: MetadataObservabilityMiddleware, from_environment<br/>📄 android_navigation_adapter.py: AndroidNavigationAdapter<br/>📄 android_network_mcp_tools.py: read_android_network_flows_snapshot, register_android_network_tools, android_network_flows_snapshot<br/>📄 automation_adapter.py: AutomationAdapter, execute<br/>📄 background_window_input.py: pack_point, click_window_background, enum_callback<br/>📄 chatgpt_plan_mcp_tools.py: register_chatgpt_plan_tools, chatgpt_plan_status<br/>📄 combined_voice_provider.py: CombinedVoiceProvider, execute<br/>📄 communication_mcp_tools.py: register_communication_tools, communication_adapters_list<br/>📄 environment_observation_publisher.py: build_desktop_observations, publish_observation, configured_observation_target<br/>📄 hardware_controller.py: HardwareController, execute<br/>📄 host_resource_diagnostics.py: collect_host_resource_diagnostics<br/>📄 host_storage_diagnostics.py: collect_host_storage_diagnostics<br/>📄 jarvis_android_mcp.py: android_device_status, android_battery_status, android_wifi_status<br/>📄 jarvis_daily_briefing.py: weather_label, geocode_enabled<br/>📄 jarvis_desktop_mcp.py: jarvis_agent_bootstrap, curiosity_capture<br/>📄 jarvis_desktop_shell.py: normalize_cloud_url, build_start_url<br/>📄 jarvis_device_registry.py: devices_db_path, ip_geolocation_enabled<br/>📄 jarvis_geospatial_intelligence.py: distance_km, filter_assets_by_radius<br/>📄 jarvis_linux_mcp.py: create_app, lifespan, main<br/>📄 jarvis_local_agent.py: JarvisLocalAgent, execute<br/>📄 keyboard_adapter.py: KeyboardAdapter, execute, type_text<br/>📄 macrodroid_adapter.py: MacroDroidAdapter, can_execute<br/>📄 mdns_discovery_adapter.py: parse_mdns_response, discover_mdns<br/>📄 navigation_gps.py: from, RouteStep, Route<br/>📄 network_discovery_adapter.py: network_interfaces<br/>📄 osint_mcp_tools.py: register_osint_tools, provider<br/>📄 portas_core.py: configurar_cdp_url, carregar_macros<br/>📄 portas_midia.py: is_media_request<br/>📄 portas_midia_entrega.py: class, class, MediaDeliveryBus<br/>📄 portas_observabilidade.py: sanitizar_url, sanitizar_payload<br/>📄 portas_utilizacao.py: executar_porta, porta<br/>📄 portas_visualizacao.py: registrar_visualizacao_portas, portas_listar<br/>📄 prospecting_demand_mcp_tools.py: register_prospecting_demand_tools, actor<br/>📄 prospecting_mcp_tools.py: resolve_principal<br/>📄 protocol_pattern_mcp_tools.py: register_protocol_pattern_tools, tracked_action, decorate<br/>📄 screen_coordinates.py: normalized_to_screen_point, enable_windows_per_monitor_dpi_awareness, screen_coordinate_spaces_compatible<br/>📄 security_audit_adapter.py: TacticalCommandPort, NearbyDevice<br/>📄 tts_adapter.py: TTSAdapter, execute<br/>📄 voice_adapter.py: VoiceAdapter, execute<br/>📄 voice_engine.py: JarvisEngine, execute<br/>📄 web_adapter.py: WebAdapter, execute<br/>📄 windows_etw_network_adapter.py: parse_tracerpt_xml<br/>📄 worker_pc.py: main"]
    class app_adapters_edge adapter
    app_adapters --> app_adapters_edge
    app_adapters_edge_host["<b>host</b><br/><hr/>📄 psutil_host_adapter.py: PsutilHostAdapter, get_identity"]
    class app_adapters_edge_host adapter
    app_adapters_edge --> app_adapters_edge_host
    app_adapters_infrastructure["<b>infrastructure</b><br/><hr/>📄 action_provider.py: ActionProvider, execute<br/>📄 agent_worker_credentials.py: from, worker_token_env_name, AgentWorkerPrincipal<br/>📄 ai_gateway.py: AIGateway<br/>📄 ai_gateway_enums.py: LLMProvider, GroqGear, AIGatewayEnums<br/>📄 ai_gateway_token_utils.py: count_tokens, TokenCounter<br/>📄 api_models.py: RequestSource, RequestMetadata, ExecuteRequest<br/>📄 api_server.py: get_current_user, create_api_server, lifespan<br/>📄 audit_logger.py: AuditLogger, configure, execute<br/>📄 auth_adapter.py: AuthAdapter, execute<br/>📄 auto_repair_mixin.py: AutoRepairMixin, must, execute<br/>📄 chatgpt_plan_auth.py: create_pkce_pair, build_authorization_url<br/>📄 chatgpt_plan_runtime.py: ChatGPTPlanError, ChatGPTPlanCredentialStore<br/>📄 consolidator.py: NexusComponent, Consolidator<br/>📄 copilot_context_provider.py: GitHubCopilotContextProvider, execute, analyzes<br/>📄 cost_tracker_adapter.py: CostTrackerAdapter<br/>📄 docker_sandbox.py: DockerSandbox, run_tests<br/>📄 drive_uploader.py: DriveUploader, configure<br/>📄 dummy_voice_provider.py: DummyVoiceProvider, execute<br/>📄 freellmapi_model_runtime.py: FreeLLMAPIModelRuntimeAdapter, invoke<br/>📄 gateway_llm_adapter.py: GatewayLLMCommandAdapter, get_system_instruction<br/>📄 gemini_adapter.py: LLMCommandAdapter, execute<br/>📄 gemini_context_manager.py: GeminiContextManager, execute<br/>📄 gemini_response_helpers.py: build_context_message, build_parameters, convert_function_call_to_intent<br/>📄 gist_uploader.py: GistUploader, execute<br/>📄 github_adapter.py: GitHubAdapter, execute<br/>📄 github_correction_adapter.py: GitHubCorrectionAdapter<br/>📄 github_issue_adapter.py: GitHubIssueAdapter, execute<br/>📄 github_issue_mixin.py: GitHubIssueMixin, provides, execute<br/>📄 github_workflow_adapter.py: GitHubWorkflowAdapter, execute<br/>📄 host_ops.py: from, PathNotAllowed<br/>📄 host_ops_mcp_tools.py: register_host_ops_tools<br/>📄 http_client.py: HttpClient<br/>📄 jrvs_cloud_storage.py: JrvsCloudStorage, execute<br/>📄 mcp_bearer_auth.py: BearerAuthMiddleware<br/>📄 mqtt_home_adapter.py: MqttHomeAdapter, execute<br/>📄 ollama_adapter.py: OllamaAdapter, configure<br/>📄 overwatch_adapter.py: OverwatchDaemon, execute<br/>📄 persistent_shell_adapter.py: PersistentShellAdapter, configure<br/>📄 playwright_worker.py: PlaywrightWorker, start<br/>📄 pyinstaller_builder.py: PyinstallerBuilder, configure, can_execute<br/>📄 respan_tracing.py: initialize_respan_tracing, shutdown_respan_tracing<br/>📄 reward_adapter.py: RewardAdapter, execute<br/>📄 reward_logger.py: RewardLogger, execute<br/>📄 secure_file_permissions.py: set_private_directory_permissions, set_private_file_permissions, verify_private_directory_permissions<br/>📄 secure_shell_navigation.py: ShellNavigator<br/>📄 setup_wizard.py: Colors, execute, print_header<br/>📄 socket_client.py: SocketClient, execute<br/>📄 soldier_bridge.py: SoldierBridgeManager, connect<br/>📄 sqlite_history_adapter.py: CoercingUTCDateTime, process_bind_param<br/>📄 supabase_client.py: get_supabase_client, is_supabase_available, get_supabase_admin_client<br/>📄 supabase_plan_journal.py: SupabasePlanEventJournal, append<br/>📄 supabase_vector_memory_store.py: SupabaseVectorMemoryStore, is_available<br/>📄 system_executor.py: SystemExecutor, configure, can_execute<br/>📄 telegram_adapter.py: TelegramAdapter<br/>📄 termux_shell.py: audit_event<br/>📄 termux_shell_mcp_tools.py: register_termux_shell_tools, android_shell_session_authenticate, android_shell_session_status<br/>📄 tool_approval_store.py: ToolApprovalStore<br/>📄 vision_adapter.py: ExternalVisionNotAllowedError, VisionAdapter<br/>📄 websocket_manager.py: WebSocketManager, execute"]
    class app_adapters_infrastructure adapter
    app_adapters --> app_adapters_infrastructure
    app_adapters_infrastructure_graph["<b>graph</b><br/><hr/>📄 sensitive_store.py: SQLiteSensitiveStore"]
    class app_adapters_infrastructure_graph adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_graph
    app_adapters_infrastructure_intelligence["<b>intelligence</b><br/><hr/>📄 laya_decision_adapter.py: LayaDecisionError, LayaDecisionAdapter<br/>📄 public_intelligence_adapter.py: PublicIntelligenceAdapter<br/>📄 supabase_intelligence_history.py: IntelligenceHistoryPersistenceError, SupabaseIntelligenceHistoryAdapter<br/>📄 supabase_intelligence_history_adapter.py: SupabaseIntelligenceHistoryAdapter<br/>📄 supabase_intelligence_worker_store.py: SupabaseIntelligenceWorkerStore"]
    class app_adapters_infrastructure_intelligence adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_intelligence
    app_adapters_infrastructure_osint["<b>osint</b><br/><hr/>📄 censys_adapter.py: CensysAdapter, query_radius<br/>📄 eagle_osint_adapter.py: EagleOsintAdapter<br/>📄 ipinfo_adapter.py: IPInfoAdapter, locate<br/>📄 shodan_adapter.py: ShodanAdapter, query_radius<br/>📄 wigle_adapter.py: WigleAdapter, query_radius"]
    class app_adapters_infrastructure_osint adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_osint
    app_adapters_infrastructure_prospecting["<b>prospecting</b><br/><hr/>📄 acate_directory.py: AcateDirectoryAdapter<br/>📄 acate_observatory.py: AcateObservatoryAdapter, load<br/>📄 cnpj_open_data.py: from, CnpjOpenDataFiles, missing<br/>📄 cnpj_store.py: from, CnpjStoreFiles, missing<br/>📄 composite.py: CompositeDiscoveryProvider<br/>📄 demand_store.py: DemandNotFound<br/>📄 external_leads.py: ExternalLeadsAdapter<br/>📄 geocodebr_geocoder.py: GeocodeBrGeocoder, geocode_companies<br/>📄 geocoding_store.py: DuckDBGeocodingRepository<br/>📄 prospecting_adapter.py: ProspectingAdapter, database_path"]
    class app_adapters_infrastructure_prospecting adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_prospecting
    app_adapters_infrastructure_routers["<b>routers</b><br/><hr/>📄 admin_recovery.py: AdminPasswordResetRequest, create_admin_recovery_router<br/>📄 agent_tasks.py: AgentHeartbeatRequest, EnqueueTaskRequest<br/>📄 assistant.py: create_assistant_router<br/>📄 bridge.py: create_bridge_router, require_authenticated_principal, local_bridge_websocket<br/>📄 dev_agent.py: create_dev_agent_router, run_dev_agent, list_dev_agent_jobs<br/>📄 devices.py: create_devices_router, register_device<br/>📄 environment_observations.py: EnvironmentObservationCreate, Config, validate_device_id<br/>📄 evolution.py: create_evolution_router, get_evolution_status<br/>📄 extensions.py: create_extensions_router, install_package, get_package_status<br/>📄 github.py: create_github_router, github_worker_operation, auto_heal_ci_failure<br/>📄 github_webhook.py: verify_github_signature, create_github_webhook_router, receive_github_webhook<br/>📄 google_identity.py: GoogleLoginRequest<br/>📄 health.py: create_health_router, health_check, health_detail<br/>📄 missions.py: create_missions_router, execute_mission, control_browser<br/>📄 mobile_push.py: MobileDeviceRegistration, MobileDeviceRevoke, MobileAgentNotification<br/>📄 mobile_sessions.py: MobileLoginRequest, MobileRefreshRequest, MobileRevokeRequest<br/>📄 network_discovery.py: DeviceInspectionRequest, CameraDiscoveryRequest, MdnsDiscoveryRequest<br/>📄 thoughts.py: create_thoughts_router, create_thought_log<br/>📄 utility.py: create_utility_router, get_api_key_guides, analyze_missing_resources"]
    class app_adapters_infrastructure_routers adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_routers
    app_adapters_infrastructure_secrets["<b>secrets</b><br/><hr/>📄 env_secrets_provider.py: EnvSecretsProvider, execute, get_secret"]
    class app_adapters_infrastructure_secrets adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_secrets
    app_application["<b>application</b><br/><hr/>📄 return_activity_service.py: class, was_idle"]
    class app_application support
    app --> app_application
    app_application_communication["<b>communication</b><br/><hr/>📄 human_intervention.py: HumanIntervention, execute"]
    class app_application_communication support
    app_application --> app_application_communication
    app_application_ports["<b>ports</b><br/><hr/>📄 action_provider.py: ActionProvider, execute, type_text<br/>📄 android_navigation.py: AndroidNavigationPort, observe_screen, tap<br/>📄 decision_engine.py: DecisionEngine, decide<br/>📄 geocoding.py: Geocoder, geocode, CompanyGeocoder<br/>📄 graph_store.py: from, UpsertReport, total<br/>📄 history_provider.py: HistoryProvider, execute, save_interaction<br/>📄 intelligence_history_repository.py: IntelligenceHistoryRepository, persist<br/>📄 intelligence_observation_source.py: IntelligenceObservationSource, collect_observations<br/>📄 intelligence_source.py: IntelligenceSource, fetch_events<br/>📄 memory_provider.py: MemoryProvider, execute, store_event<br/>📄 model_runtime.py: from, ModelMessage<br/>📄 osint_discovery.py: GeoProvider, locate, NetworkResolver<br/>📄 osint_provider.py: OsintProvider, search<br/>📄 reward_provider.py: RewardProvider, execute, log_reward<br/>📄 security_provider.py: SecurityProvider, execute, verify_password<br/>📄 soldier_provider.py: SoldierProvider, execute, register_soldier<br/>📄 system_controller.py: SystemController, execute_command, is_available<br/>📄 tactical_command_port.py: TacticalCommandPort, execute, execute_security_payload<br/>📄 vector_memory_store.py: VectorMemoryStore, is_available, is_healthy<br/>📄 visual_navigation.py: VisualNavigationPort, execute<br/>📄 voice_provider.py: VoiceProvider, execute, speak<br/>📄 web_provider.py: WebProvider, execute, open_url"]
    class app_application_ports port
    app_application --> app_application_ports
    app_application_privacy["<b>privacy</b><br/><hr/>📄 pii_redactor.py: PiiRedactor, execute"]
    class app_application_privacy support
    app_application --> app_application_privacy
    app_application_prospecting["<b>prospecting</b><br/><hr/>📄 campaign.py: CampaignDefinition, validate_same_tenant, RunManifest<br/>📄 demand_discovery.py: DemandSearchHit, DemandSearchResult, DemandDiscoveryService<br/>📄 history.py: SnapshotCompany, RunSnapshot, SnapshotChange<br/>📄 outreach.py: from"]
    class app_application_prospecting support
    app_application --> app_application_prospecting
    app_application_security["<b>security</b><br/><hr/>📄 capability_authorizer.py: CapabilityAuthorizer, can_execute<br/>📄 repository_path_policy.py: UnsafeRepositoryPath, normalize_relative_path, validate_filename"]
    class app_application_security support
    app_application --> app_application_security
    app_application_services["<b>services</b><br/><hr/>📄 adapter_registry.py: from, CapabilityGap, ready<br/>📄 agent_task_queue_service.py: TaskQueueUnavailable, AgentTaskQueueService<br/>📄 assistant_curiosity.py: maybe_inject_curiosity_question, capture_curiosity_answer<br/>📄 assistant_learning.py: check_internal_solution, record_learning_interaction, infer_task_type<br/>📄 assistant_lifecycle.py: health_check_loop, start_service, stop_service<br/>📄 assistant_nexus.py: nexus_execute, nexus_can_execute, async_process_command<br/>📄 assistant_proactivity.py: maybe_get_proactive_suggestion<br/>📄 assistant_service.py: AssistantService<br/>📄 auto_evolutionV2.py: AutoEvolutionServiceV2, execute<br/>📄 browser_manager.py: PersistentBrowserManager, execute<br/>📄 c2_orchestrator_service.py: KeepAliveProvider, start<br/>📄 capability_blueprint_service.py: CapabilityBlueprintService, execute<br/>📄 capability_detectors.py: detect_capability_inventory, detect_capability_classification, detect_existing_capabilities_recognition<br/>📄 capability_gap_reporter.py: CapabilityGapReporter, execute<br/>📄 capability_impact_analyzer.py: CapabilityImpactAnalyzer, execute<br/>📄 capability_manager.py: CapabilityManager, execute, implements<br/>📄 consolidated_context_service.py: ConsolidatedContextService, can_execute<br/>📄 curiosity_engine.py: CuriosityEngine<br/>📄 curiosity_intake.py: CuriosityIntake, configure<br/>📄 dependency_manager.py: DependencyManager, ensure_capability<br/>📄 device_capability_service.py: DeviceLocationService, calculate_distance<br/>📄 device_intent_translator.py: DeviceIntentTranslator, can_execute, execute<br/>📄 device_location_service.py: DeviceLocationService, execute, calculate_distance<br/>📄 device_orchestrator_service.py: SoldierDB, DeviceOrchestratorService<br/>📄 device_service.py: DeviceService, execute<br/>📄 evaluate_risks_service.py: EvaluateRisksService, execute<br/>📄 evolution_gatekeeper.py: EvolutionGatekeeper, configure<br/>📄 evolution_loop.py: EvolutionLoopService, configure<br/>📄 evolution_orchestrator.py: EvolutionOrchestrator, configure<br/>📄 evolution_sandbox.py: EvolutionSandbox, enabled<br/>📄 extension_manager.py: ExtensionManager, execute<br/>📄 field_vision.py: FieldVision<br/>📄 finetune_dataset_collector.py: FineTuneDatasetCollector, configure<br/>📄 finetune_trigger_service.py: FineTuneTriggerService, configure<br/>📄 github_worker.py: GitHubWorker<br/>📄 graph_enrichment.py: GraphEnrichmentService, enrich_scope<br/>📄 graph_expander_setup.py: configure_graph_expanders, get_graph_expander_registry<br/>📄 graph_retention.py: GraphRetentionService, prune_scope<br/>📄 graph_store_setup.py: graph_db_path, get_graph_store, reset_graph_store<br/>📄 human_intervention_service.py: HumanInterventionService, execute<br/>📄 identify_mission_critical_capabilities.py: identify_mission_critical_capabilities<br/>📄 intelligence_core.py: IntelligenceCore, process<br/>📄 intelligence_recurring_worker.py: from, IntelligenceWorkerConfig<br/>📄 interface_bridge.py: InterfaceBridge, execute<br/>📄 jrvs_translator.py: JrvsTranslator, execute<br/>📄 laya_decision_shadow.py: LayaDecisionShadowObserver, submit<br/>📄 llm_capability_detector.py: LLMCapabilityDetector, execute<br/>📄 llm_capability_prompt_builder.py: extract_keywords, search_files_by_keywords, build_analysis_prompt<br/>📄 llm_router.py: LLMRouter, configure<br/>📄 llm_service.py: LlmService, chat<br/>📄 local_bridge.py: LocalBridgeManager, execute<br/>📄 local_repair_agent.py: LocalRepairAgent, execute<br/>📄 location_service.py: LocationService, execute<br/>📄 main.py: notify_online, run_api, background_bootstrap<br/>📄 memory_consolidation_service.py: MemoryConsolidationService<br/>📄 memory_manager.py: MemoryManager, execute<br/>📄 meta_reflection.py: MetaReflection, configure<br/>📄 metabolism_core.py: MetabolismCore, execute, ask_jarvis<br/>📄 model_orchestrator.py: ModelOrchestrator, configure<br/>📄 notification_service.py: NotificationService, execute<br/>📄 orchestrator_service.py: OrchestratorService, execute<br/>📄 osint_adapter_setup.py: configure_osint_adapters, get_osint_registry<br/>📄 osint_discovery.py: RateLimitExceeded, InMemoryTTLCache<br/>📄 osint_fusion.py: OSINTFusion, fuse<br/>📄 presence_service.py: from, PresenceState, PresenceSnapshot<br/>📄 prioritizer_service.py: PrioritizerService, execute<br/>📄 proactive_initiative_engine.py: from, InitiativeCandidate, to_dict<br/>📄 reconnection_briefing.py: ReconnectionBriefing, execute<br/>📄 roadmap_mission_selector.py: RoadmapManifestError, RoadmapMissionSelector<br/>📄 run_workflow.py: RunWorkflow, execute<br/>📄 scavenger_hunt.py: logger, class, ScavengerHunt<br/>📄 serve.py: setup_telegram_webhook<br/>📄 soldier_registry.py: SoldierRegistry, execute<br/>📄 status_service.py: StatusService, get_system_report<br/>📄 strategist_service.py: BudgetExceededException, StrategistService<br/>📄 structured_logger.py: StructuredLogger, execute<br/>📄 surgical_edit_service.py: SurgicalEditService, apply_surgical_edit<br/>📄 tactical_map_service.py: TacticalMapService, execute<br/>📄 task_runner.py: TaskRunner<br/>📄 technical_analysis_service.py: TechnicalAnalysisService, execute<br/>📄 thought_log_renderer.py: ThoughtRenderer, render<br/>📄 thought_log_service.py: ThoughtLogService, create_thought<br/>📄 thought_log_storage.py: ThoughtLogStorage, db<br/>📄 thought_log_types.py: ThoughtType<br/>📄 user_communication_service.py: from, CommunicationPriority, CommunicationDecision<br/>📄 vocal_orchestration_service.py: VocalOrchestrationService"]
    class app_application_services support
    app_application --> app_application_services
    app_application_services_crystallization["<b>crystallization</b><br/><hr/>📄 crystallizer_engine.py: CrystallizerEngine, execute"]
    class app_application_services_crystallization support
    app_application_services --> app_application_services_crystallization
    app_application_services_jarvis_dev_agent["<b>jarvis_dev_agent</b><br/><hr/>📄 agent.py: JarvisDevAgent, configure"]
    class app_application_services_jarvis_dev_agent support
    app_application_services --> app_application_services_jarvis_dev_agent
    app_application_services_prospecting["<b>prospecting</b><br/><hr/>📄 geocoding.py: GeocodingService, geocode"]
    class app_application_services_prospecting support
    app_application_services --> app_application_services_prospecting
    app_communication["<b>communication</b><br/><hr/>📄 bootstrap.py: create_default_communication_registry<br/>📄 capture.py: redact_secrets<br/>📄 chatgpt_plan.py: ChatGPTPlanCommunicationAdapter, send_prompt<br/>📄 contracts.py: CommunicationRequest, CommunicationCaptureRecord<br/>📄 dispatcher.py: create_chatgpt_plan_dispatcher, resolve_principal<br/>📄 registry.py: CommunicationRegistry, register<br/>📄 replay.py: CommunicationReplay, execute"]
    class app_communication support
    app --> app_communication
    app_core["<b>core</b><br/><hr/>📄 config.py: Settings, decrypt_api_key, decrypt_database_url<br/>📄 encryption.py: get_hardware_id, derive_key_from_hardware, encrypt_value<br/>📄 llm_config.py: LLMConfig, use_llm_command_interpretation, use_llm_capability_detection<br/>📄 nexus.py: JarvisNexus<br/>📄 nexus_discovery.py: finders<br/>📄 nexus_exceptions.py: ImportTimeoutError, InstantiateTimeoutError, instantiation<br/>📄 nexuscomponent.py: NexusComponent<br/>📄 operating_profiles.py: from, OperatingProfile<br/>📄 recovery_store.py: RecoveryError"]
    class app_core core
    app --> app_core
    app_core_meta["<b>meta</b><br/><hr/>📄 compile_lock.py: acquire_compile_lock<br/>📄 decision_engine.py: class, DecisionEngine<br/>📄 exploration_controller.py: ExplorationController, execute<br/>📄 jrvs_compiler.py: SchemaVersionError, JRVSCompiler<br/>📄 policy_store.py: PolicyStore, get_policies_by_module"]
    class app_core_meta core
    app_core --> app_core_meta
    app_domain["<b>domain</b>"]
    class app_domain support
    app --> app_domain
    app_domain_ai["<b>ai</b><br/><hr/>📄 gemini_service.py: GeminiService, execute"]
    class app_domain_ai support
    app_domain --> app_domain_ai
    app_domain_analysis["<b>analysis</b><br/><hr/>📄 performance_analyzer.py: PerformanceAnalyzer, execute"]
    class app_domain_analysis support
    app_domain --> app_domain_analysis
    app_domain_capabilities["<b>capabilities</b><br/><hr/>📄 cap_001.py: Cap001, configure<br/>📄 cap_002.py: Cap002, configure<br/>📄 cap_003.py: Cap003, configure<br/>📄 cap_004.py: Cap004, configure<br/>📄 cap_005.py: Cap005, configure<br/>📄 cap_006.py: Cap006, configure<br/>📄 cap_007.py: Cap007, configure<br/>📄 cap_008.py: Cap008, configure<br/>📄 cap_009.py: Cap009, execute<br/>📄 cap_010.py: Cap010, execute<br/>📄 cap_011.py: Cap011, execute<br/>📄 cap_012.py: Cap012, execute<br/>📄 cap_013.py: Cap013, execute<br/>📄 cap_014.py: Cap014, execute<br/>📄 cap_015.py: Cap015, execute<br/>📄 cap_016.py: Cap016, execute<br/>📄 cap_017.py: Cap017, execute<br/>📄 cap_018.py: Cap018, execute<br/>📄 cap_019.py: Cap019, execute<br/>📄 cap_020.py: Cap020, execute<br/>📄 cap_021.py: Cap021, execute<br/>📄 cap_022.py: Cap022, execute<br/>📄 cap_023.py: Cap023, configure<br/>📄 cap_024.py: Cap024, execute<br/>📄 cap_025.py: Cap025, execute<br/>📄 cap_026.py: Cap026, execute<br/>📄 cap_027.py: Cap027, configure<br/>📄 cap_028.py: Cap028, execute<br/>📄 cap_029.py: Cap029, execute<br/>📄 cap_030.py: Cap030, execute<br/>📄 cap_031.py: Cap031, execute<br/>📄 cap_032.py: Cap032, configure<br/>📄 cap_033.py: Cap033, configure<br/>📄 cap_034.py: Cap034, configure<br/>📄 cap_035.py: Cap035, execute<br/>📄 cap_036.py: Cap036, execute<br/>📄 cap_037.py: Cap037, execute<br/>📄 cap_038.py: Cap038, execute<br/>📄 cap_039.py: Cap039, configure<br/>📄 cap_040.py: Cap040, configure<br/>📄 cap_041.py: Cap041, execute<br/>📄 cap_042.py: Cap042, execute<br/>📄 cap_043.py: Cap043, execute<br/>📄 cap_044.py: Cap044, configure<br/>📄 cap_045.py: Cap045, configure<br/>📄 cap_046.py: Cap046, execute<br/>📄 cap_047.py: Cap047, configure<br/>📄 cap_048.py: Cap048, execute<br/>📄 cap_049.py: Cap049, execute<br/>📄 cap_050.py: Cap050, execute<br/>📄 cap_051.py: Cap051, execute<br/>📄 cap_052.py: Cap052, execute<br/>📄 cap_053.py: Cap053, execute<br/>📄 cap_054.py: Cap054, execute<br/>📄 cap_055.py: Cap055, execute<br/>📄 cap_056.py: Cap056, execute<br/>📄 cap_057.py: Cap057, configure<br/>📄 cap_058.py: Cap058, execute<br/>📄 cap_059.py: Cap059, configure<br/>📄 cap_060.py: Cap060, execute<br/>📄 cap_061.py: Cap061, execute<br/>📄 cap_062.py: Cap062, execute<br/>📄 cap_063.py: Cap063, execute<br/>📄 cap_064.py: Cap064, execute<br/>📄 cap_065.py: Cap065, execute<br/>📄 cap_066.py: Cap066, execute<br/>📄 cap_067.py: Cap067, configure<br/>📄 cap_068.py: Cap068, execute<br/>📄 cap_069.py: Cap069, execute<br/>📄 cap_070.py: Cap070, execute<br/>📄 cap_071.py: Cap071, execute<br/>📄 cap_072.py: Cap072, configure<br/>📄 cap_073.py: Cap073, execute<br/>📄 cap_074.py: Cap074, execute<br/>📄 cap_075.py: Cap075, execute<br/>📄 cap_076.py: Cap076, execute<br/>📄 cap_077.py: Cap077, execute<br/>📄 cap_078.py: Cap078, execute<br/>📄 cap_079.py: Cap079, execute<br/>📄 cap_080.py: Cap080, execute<br/>📄 cap_081.py: Cap081, execute<br/>📄 cap_082.py: Cap082, execute<br/>📄 cap_083.py: Cap083, execute<br/>📄 cap_084.py: Cap084, execute<br/>📄 cap_085.py: Cap085, execute<br/>📄 cap_086.py: Cap086, execute<br/>📄 cap_087.py: Cap087, execute<br/>📄 cap_088.py: Cap088, execute<br/>📄 cap_089.py: Cap089, execute<br/>📄 cap_090.py: Cap090, execute<br/>📄 cap_091.py: Cap091, execute<br/>📄 cap_092.py: Cap092, execute<br/>📄 cap_093.py: Cap093, execute<br/>📄 cap_094.py: Cap094, execute<br/>📄 cap_095.py: Cap095, configure<br/>📄 cap_096.py: Cap096, execute<br/>📄 cap_097.py: Cap097, execute<br/>📄 cap_098.py: Cap098, execute<br/>📄 cap_099.py: Cap099, execute<br/>📄 cap_100.py: Cap100, configure<br/>📄 cap_101.py: Cap101, execute<br/>📄 cap_102.py: Cap102, execute<br/>📄 context_memory.py: ContextMemory, configure, execute"]
    class app_domain_capabilities support
    app_domain --> app_domain_capabilities
    app_domain_context["<b>context</b><br/><hr/>📄 context_manager.py: SystemContext, ContextManager"]
    class app_domain_context support
    app_domain --> app_domain_context
    app_domain_gears["<b>gears</b><br/><hr/>📄 cognitive_router.py: CognitiveRouter, configure<br/>📄 llm_engine.py: LlmEngine, configure"]
    class app_domain_gears support
    app_domain --> app_domain_gears
    app_domain_graph["<b>graph</b><br/><hr/>📄 confidence.py: is_strong_pivot, edge_confidence<br/>📄 edges.py: PivotType, edge_id, Edge<br/>📄 expander.py: from, ExpansionCost, Expansion<br/>📄 fuse.py: haversine_km, Fuse<br/>📄 graph.py: GraphIntegrityError, GraphDelta<br/>📄 loop.py: from, LoopPolicy<br/>📄 nodes.py: NodeType, only_digits<br/>📄 policy.py: from, GraphPolicyError, for<br/>📄 pruner.py: PrunePolicy, ttl_for<br/>📄 registry.py: from, GapReport, ready<br/>📄 resolver.py: AdapterBoundaryError<br/>📄 sensitive_store.py: utcnow, as_utc, AccessRecord"]
    class app_domain_graph support
    app_domain --> app_domain_graph
    app_domain_intelligence["<b>intelligence</b><br/><hr/>📄 contracts.py: GeoPoint, IntelligenceEvidence, IntelligenceEvent<br/>📄 osint.py: Coordinate, finite_values, NetworkRange"]
    class app_domain_intelligence support
    app_domain --> app_domain_intelligence
    app_domain_memory["<b>memory</b><br/><hr/>📄 prospective_memory.py: ProspectiveMemory<br/>📄 semantic_memory.py: SemanticMemory, configure<br/>📄 working_memory.py: WorkingMemoryEntry, WorkingMemory"]
    class app_domain_memory support
    app_domain --> app_domain_memory
    app_domain_missions["<b>missions</b><br/><hr/>📄 mission_selector.py: MissionSelector, execute"]
    class app_domain_missions support
    app_domain --> app_domain_missions
    app_domain_models["<b>models</b><br/><hr/>📄 adapter_registry.py: class, to_dict, AdapterRegistry<br/>📄 agent.py: ActionType, TaskSource, TaskPriority<br/>📄 capability.py: JarvisCapability, execute<br/>📄 capability_alias_registry.py: from, AliasRegistryError, UnknownAliasError<br/>📄 command.py: CommandType, Intent<br/>📄 device.py: Device, execute, Capability<br/>📄 evolution_reward.py: EvolutionReward, execute<br/>📄 mission.py: class, execute, to_dict<br/>📄 soldier.py: SoldierStatus, SoldierRegistration, soldier_id_not_empty<br/>📄 system_state.py: SystemStatus, execute, Config<br/>📄 thought_log.py: InteractionStatus, ThoughtLog, Config<br/>📄 viability.py: RiskLevel, ImpactLevel, class"]
    class app_domain_models support
    app_domain --> app_domain_models
    app_domain_orchestration["<b>orchestration</b><br/><hr/>📄 central_orchestrator.py: CentralOrchestrator, execute"]
    class app_domain_orchestration support
    app_domain --> app_domain_orchestration
    app_domain_ports["<b>ports</b><br/><hr/>📄 device_control_port.py: from, class, DeviceControlPort<br/>📄 host_port.py: from, HostIdentity, DiskUsage"]
    class app_domain_ports port
    app_domain --> app_domain_ports
    app_domain_prospecting["<b>prospecting</b><br/><hr/>📄 contracts.py: ProspectEvidenceType, RegistryPresence, ProspectStage<br/>📄 deliverable.py: DeliverableRow, validate_same_prospect_and_tenant<br/>📄 demand.py: RequesterType, MarketDirection, DemandIntent<br/>📄 discovery.py: DiscoveryQuery, validate_cursor, normalize_uf<br/>📄 filters.py: FilterPreset, FilterCatalog, get<br/>📄 geography.py: GeocodingStatus, GeocodingPrecision, GeoCoordinate<br/>📄 icp.py: FitCriterion, CriterionOutcome, IcpWeights<br/>📄 lifecycle.py: InvalidProspectTransition, transition_prospect<br/>📄 market_intelligence.py: MarketIndicator, validate_reference_period, MarketIndicatorDataset<br/>📄 qualification.py: IntentSignalType, IntentStrength, QualificationTier<br/>📄 source_registry.py: SourceKind, AcquisitionMode, SourceStatus"]
    class app_domain_prospecting support
    app_domain --> app_domain_prospecting
    app_domain_services["<b>services</b><br/><hr/>📄 agent_service.py: AgentService, execute<br/>📄 command_interpreter.py: CommandInterpreter, execute<br/>📄 intent_processor.py: IntentProcessor<br/>📄 llm_command_interpreter.py: LLMCommandInterpreter, execute<br/>📄 reward_signal_provider.py: record<br/>📄 safety_guardian.py: SafetyGuardian, configure<br/>📄 soldier_shield.py: SoldierShield, execute<br/>📄 state_manager.py: StateManager, execute<br/>📄 system_state_tracker.py: SystemStateTracker, execute<br/>📄 vocal_orchestrator.py: VocalOrchestrator, execute"]
    class app_domain_services support
    app_domain --> app_domain_services
    app_domain_tools["<b>tools</b><br/><hr/>📄 contracts.py: HealthPolicy, validate_periodic_interval, RateLimitPolicy<br/>📄 registry.py: DuplicateToolManifestError, ToolRegistry"]
    class app_domain_tools support
    app_domain --> app_domain_tools
    app_multiagent["<b>multiagent</b><br/><hr/>📄 agent_worker_runtime.py: run_worker_loop, WorkerGroup<br/>📄 contracts.py: TaskStatus, AgentProfile<br/>📄 execution_plan.py: from, PlanValidationError, StepOutcome<br/>📄 freellmapi_client.py: configured_provider_id, FreeLLMAPIError<br/>📄 freellmapi_handler.py: FreeLLMAgentHandler, close<br/>📄 leader.py: from, class, AgentLeader<br/>📄 model_plan_adapter.py: extract_json_object, repair_model_plan<br/>📄 model_registry.py: ModelProfile<br/>📄 model_runtime_factory.py: ChatGPTPlanOAuthPort, load_valid_profile, get_access_token<br/>📄 priority_queue_mini_agent.py: PriorityQueueMiniAgent, from_env<br/>📄 scheduler.py: from, NoEligibleAgentError<br/>📄 supabase_queue.py: SupabaseQueueConnector, send<br/>📄 supabase_store.py: SupabaseAgentStore, register_agent<br/>📄 supabase_task_worker.py: SupabaseTaskQueueMiniAgent, from_env<br/>📄 transport.py: AgentMessage, create, to_dict<br/>📄 worker.py: AcknowledgingConnector, send, receive"]
    class app_multiagent support
    app --> app_multiagent
    app_plugins["<b>plugins</b><br/><hr/>📄 plugin_loader.py: PluginLoader, execute"]
    class app_plugins support
    app --> app_plugins
    app_plugins_dynamic["<b>dynamic</b><br/><hr/>📄 example_plugin.py: hello_jarvis, register, PluginCapability"]
    class app_plugins_dynamic support
    app_plugins --> app_plugins_dynamic
    app_ports["<b>ports</b><br/><hr/>📄 secrets_provider.py: SecretsProvider, get_secret<br/>📄 voice_port.py: VoicePort, stt, tts"]
    class app_ports port
    app --> app_ports
    app_runtime["<b>runtime</b><br/><hr/>📄 pipeline_runner.py: CloudMock, run_pipeline"]
    class app_runtime support
    app --> app_runtime
    app_runtime_toolbox["<b>toolbox</b><br/><hr/>📄 audit.py: JsonlToolAuditSink<br/>📄 authorization.py: ToolAuthorizationPolicy, authorize_tool<br/>📄 contracts.py: ToolRequest, ToolResult, ToolAuthorizationDecision<br/>📄 host_authorization.py: TrustedToolPrincipal, validate_identity_fields, validate_capability_grants<br/>📄 toolchains.py: ToolchainStep, ToolchainManifest, from_file"]
    class app_runtime_toolbox support
    app_runtime --> app_runtime_toolbox
    app_static["<b>static</b>"]
    class app_static support
    app --> app_static
    app_utils["<b>utils</b><br/><hr/>📄 document_store.py: DocumentStore, read, write<br/>📄 helpers.py: setup_logging, ensure_directory, sanitize_filename<br/>📄 jrvs_codec.py: JrvsDecodeError, encode, decode"]
    class app_utils support
    app --> app_utils
    config["<b>config</b>"]
    class config support
    config_pipelines["<b>pipelines</b>"]
    class config_pipelines support
    config --> config_pipelines
    config_prospecting["<b>prospecting</b>"]
    class config_prospecting support
    config --> config_prospecting
    config_prospecting_campaigns["<b>campaigns</b>"]
    class config_prospecting_campaigns support
    config_prospecting --> config_prospecting_campaigns
    config_toolchains["<b>toolchains</b>"]
    class config_toolchains support
    config --> config_toolchains
    dags["<b>dags</b><br/><hr/>📄 jarvis_status_dag.py: get_assistant_status, send_notification"]
    class dags support
    desktop["<b>desktop</b>"]
    class desktop support
    linux["<b>linux</b>"]
    class linux support
    linux_systemd["<b>systemd</b>"]
    class linux_systemd support
    linux --> linux_systemd
    migrations["<b>migrations</b>"]
    class migrations support
    mobile["<b>mobile</b>"]
    class mobile support
    mobile_android["<b>android</b>"]
    class mobile_android support
    mobile --> mobile_android
    mobile_android_THIRD_PARTY_LICENSES["<b>THIRD_PARTY_LICENSES</b>"]
    class mobile_android_THIRD_PARTY_LICENSES support
    mobile_android --> mobile_android_THIRD_PARTY_LICENSES
    mobile_android_app["<b>app</b>"]
    class mobile_android_app support
    mobile_android --> mobile_android_app
    mobile_android_app_src["<b>src</b>"]
    class mobile_android_app_src support
    mobile_android_app --> mobile_android_app_src
    mobile_android_app_src_main["<b>main</b>"]
    class mobile_android_app_src_main support
    mobile_android_app_src --> mobile_android_app_src_main
    mobile_android_app_src_main_java["<b>java</b>"]
    class mobile_android_app_src_main_java support
    mobile_android_app_src_main --> mobile_android_app_src_main_java
    mobile_android_app_src_main_java_com["<b>com</b>"]
    class mobile_android_app_src_main_java_com support
    mobile_android_app_src_main_java --> mobile_android_app_src_main_java_com
    mobile_android_app_src_main_java_com_thedrack["<b>thedrack</b>"]
    class mobile_android_app_src_main_java_com_thedrack support
    mobile_android_app_src_main_java_com --> mobile_android_app_src_main_java_com_thedrack
    mobile_android_app_src_main_java_com_thedrack_jarvismobile["<b>jarvismobile</b>"]
    class mobile_android_app_src_main_java_com_thedrack_jarvismobile support
    mobile_android_app_src_main_java_com_thedrack --> mobile_android_app_src_main_java_com_thedrack_jarvismobile
    mobile_android_app_src_main_res["<b>res</b>"]
    class mobile_android_app_src_main_res support
    mobile_android_app_src_main --> mobile_android_app_src_main_res
    mobile_android_app_src_main_res_values["<b>values</b>"]
    class mobile_android_app_src_main_res_values support
    mobile_android_app_src_main_res --> mobile_android_app_src_main_res_values
    mobile_android_app_src_main_res_xml["<b>xml</b>"]
    class mobile_android_app_src_main_res_xml support
    mobile_android_app_src_main_res --> mobile_android_app_src_main_res_xml
    mobile_android_app_src_test["<b>test</b>"]
    class mobile_android_app_src_test support
    mobile_android_app_src --> mobile_android_app_src_test
    mobile_android_app_src_test_java["<b>java</b>"]
    class mobile_android_app_src_test_java support
    mobile_android_app_src_test --> mobile_android_app_src_test_java
    mobile_android_app_src_test_java_com["<b>com</b>"]
    class mobile_android_app_src_test_java_com support
    mobile_android_app_src_test_java --> mobile_android_app_src_test_java_com
    mobile_android_app_src_test_java_com_thedrack["<b>thedrack</b>"]
    class mobile_android_app_src_test_java_com_thedrack support
    mobile_android_app_src_test_java_com --> mobile_android_app_src_test_java_com_thedrack
    mobile_android_app_src_test_java_com_thedrack_jarvismobile["<b>jarvismobile</b>"]
    class mobile_android_app_src_test_java_com_thedrack_jarvismobile support
    mobile_android_app_src_test_java_com_thedrack --> mobile_android_app_src_test_java_com_thedrack_jarvismobile
    requirements["<b>requirements</b>"]
    class requirements support
    skills["<b>skills</b>"]
    class skills support
    skills_jarvis-android-navigation["<b>jarvis-android-navigation</b>"]
    class skills_jarvis-android-navigation support
    skills --> skills_jarvis-android-navigation
    skills_jarvis-context-memory["<b>jarvis-context-memory</b>"]
    class skills_jarvis-context-memory support
    skills --> skills_jarvis-context-memory
    skills_jarvis-host-ops["<b>jarvis-host-ops</b>"]
    class skills_jarvis-host-ops support
    skills --> skills_jarvis-host-ops
    skills_jarvis-mobile-notifications["<b>jarvis-mobile-notifications</b>"]
    class skills_jarvis-mobile-notifications support
    skills --> skills_jarvis-mobile-notifications
    skills_jarvis-multi-agent-coordination["<b>jarvis-multi-agent-coordination</b>"]
    class skills_jarvis-multi-agent-coordination support
    skills --> skills_jarvis-multi-agent-coordination
    skills_jarvis-portas-browser["<b>jarvis-portas-browser</b>"]
    class skills_jarvis-portas-browser support
    skills --> skills_jarvis-portas-browser
    skills_jarvis-visual-navigation["<b>jarvis-visual-navigation</b>"]
    class skills_jarvis-visual-navigation support
    skills --> skills_jarvis-visual-navigation
    skills_jarvis-viv["<b>jarvis-viv</b>"]
    class skills_jarvis-viv support
    skills --> skills_jarvis-viv
    static["<b>static</b>"]
    class static support
    supabase["<b>supabase</b>"]
    class supabase support
    supabase__temp["<b>.temp</b>"]
    class supabase__temp support
    supabase --> supabase__temp
    supabase_migrations["<b>migrations</b>"]
    class supabase_migrations support
    supabase --> supabase_migrations
```
